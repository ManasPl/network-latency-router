from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from . import models, schemas
from .database import Base, engine, get_db
from .routing import build_graph, shortest_path

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Network Route Optimization API", version="1.0.0")

# allow the API checker page to call the API even when opened as a local file
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CHECKER_PAGE = Path(__file__).resolve().parent.parent / "static" / "api-checker.html"


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/check", include_in_schema=False)
def checker_page():
    return FileResponse(CHECKER_PAGE)


# return all errors as {"error": "..."}
@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    # FastAPI returns 422 by default, the spec expects 400
    messages = []
    for err in exc.errors():
        field = str(err["loc"][-1]) if len(err["loc"]) > 1 else ""
        msg = err["msg"].replace("Value error, ", "")
        if field:
            messages.append(f"{field}: {msg}")
        else:
            messages.append(msg)
    return JSONResponse(status_code=400, content={"error": "; ".join(messages)})


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def get_node_by_name(db: Session, name: str) -> Optional[models.Node]:
    return db.scalar(select(models.Node).where(models.Node.name == name))


def edge_out(edge: models.Edge) -> schemas.EdgeOut:
    return schemas.EdgeOut(
        id=edge.id, source=edge.source.name, destination=edge.destination.name, latency=edge.latency
    )


@app.post("/nodes", response_model=schemas.NodeOut, status_code=status.HTTP_201_CREATED)
def create_node(payload: schemas.NodeCreate, db: Session = Depends(get_db)):
    if get_node_by_name(db, payload.name):
        raise bad_request(f"Node '{payload.name}' already exists")
    node = models.Node(name=payload.name)
    db.add(node)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise bad_request(f"Node '{payload.name}' already exists")
    db.refresh(node)
    return node


@app.get("/nodes", response_model=List[schemas.NodeOut])
def list_nodes(db: Session = Depends(get_db)):
    return db.scalars(select(models.Node).order_by(models.Node.id)).all()


@app.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(node_id: int, db: Session = Depends(get_db)):
    node = db.get(models.Node, node_id)
    if not node:
        raise not_found(f"Node with id {node_id} not found")
    db.delete(node)  # edges get deleted too (cascade)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/edges", response_model=schemas.EdgeOut, status_code=status.HTTP_201_CREATED)
def create_edge(payload: schemas.EdgeCreate, db: Session = Depends(get_db)):
    if payload.source == payload.destination:
        raise bad_request("Source and destination must be different nodes")

    source = get_node_by_name(db, payload.source)
    destination = get_node_by_name(db, payload.destination)
    missing = []
    if source is None:
        missing.append(payload.source)
    if destination is None:
        missing.append(payload.destination)
    if missing:
        raise bad_request(f"Node(s) not found: {', '.join(missing)}")

    duplicate_msg = f"Edge from '{payload.source}' to '{payload.destination}' already exists"
    exists = db.scalar(
        select(models.Edge.id).where(
            models.Edge.source_id == source.id, models.Edge.destination_id == destination.id
        )
    )
    if exists:
        raise bad_request(duplicate_msg)

    edge = models.Edge(source_id=source.id, destination_id=destination.id, latency=payload.latency)
    db.add(edge)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise bad_request(duplicate_msg)
    db.refresh(edge)
    return edge_out(edge)


@app.get("/edges", response_model=List[schemas.EdgeOut])
def list_edges(db: Session = Depends(get_db)):
    edges = db.scalars(select(models.Edge).order_by(models.Edge.id)).all()
    return [edge_out(e) for e in edges]


@app.delete("/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edge(edge_id: int, db: Session = Depends(get_db)):
    edge = db.get(models.Edge, edge_id)
    if not edge:
        raise not_found(f"Edge with id {edge_id} not found")
    db.delete(edge)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/routes/shortest", response_model=schemas.RouteOut)
def get_shortest_route(payload: schemas.RouteRequest, db: Session = Depends(get_db)):
    missing = []
    if get_node_by_name(db, payload.source) is None:
        missing.append(payload.source)
    if payload.destination != payload.source and get_node_by_name(db, payload.destination) is None:
        missing.append(payload.destination)
    if missing:
        raise bad_request(f"Node(s) not found: {', '.join(missing)}")

    src, dst = aliased(models.Node), aliased(models.Node)
    rows = db.execute(
        select(src.name, dst.name, models.Edge.latency)
        .join(src, models.Edge.source_id == src.id)
        .join(dst, models.Edge.destination_id == dst.id)
    ).all()

    result = shortest_path(build_graph(rows), payload.source, payload.destination)
    if result is None:
        raise not_found(f"No path exists between {payload.source} and {payload.destination}")

    total_latency, path = result
    db.add(
        models.RouteQuery(
            source=payload.source,
            destination=payload.destination,
            total_latency=total_latency,
            path=path,
        )
    )
    db.commit()
    return schemas.RouteOut(total_latency=total_latency, path=path)


def to_utc(dt: datetime) -> datetime:
    # created_at is saved as naive UTC, so convert the filter dates the same way
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@app.get("/routes/history", response_model=List[schemas.RouteHistoryOut])
def get_route_history(
    source: Optional[str] = None,
    destination: Optional[str] = None,
    limit: Optional[int] = Query(None, ge=1, le=1000),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    if date_from and date_to and to_utc(date_from) > to_utc(date_to):
        raise bad_request("date_from must be earlier than or equal to date_to")

    q = select(models.RouteQuery)
    if source:
        q = q.where(models.RouteQuery.source == source.strip())
    if destination:
        q = q.where(models.RouteQuery.destination == destination.strip())
    if date_from:
        q = q.where(models.RouteQuery.created_at >= to_utc(date_from))
    if date_to:
        q = q.where(models.RouteQuery.created_at <= to_utc(date_to))
    q = q.order_by(models.RouteQuery.created_at.desc(), models.RouteQuery.id.desc())
    if limit:
        q = q.limit(limit)
    return db.scalars(q).all()
