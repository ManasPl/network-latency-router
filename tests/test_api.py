import os
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_network.db"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.routing import shortest_path, build_graph

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def add_nodes(*names):
    for n in names:
        assert client.post("/nodes", json={"name": n}).status_code == 201


def add_edge(src, dst, latency):
    r = client.post("/edges", json={"source": src, "destination": dst, "latency": latency})
    assert r.status_code == 201, r.json()
    return r.json()


def test_create_node():
    r = client.post("/nodes", json={"name": "ServerA"})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "name": "ServerA"}


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "   "}, {"name": None}, {"name": 5}])
def test_create_node_invalid(body):
    r = client.post("/nodes", json=body)
    assert r.status_code == 400
    assert "error" in r.json()


def test_create_node_duplicate():
    add_nodes("ServerA")
    r = client.post("/nodes", json={"name": "ServerA"})
    assert r.status_code == 400
    assert "already exists" in r.json()["error"]


def test_list_and_delete_node_cascades_edges():
    add_nodes("A", "B", "C")
    add_edge("A", "B", 1)
    add_edge("B", "C", 1)
    assert [n["name"] for n in client.get("/nodes").json()] == ["A", "B", "C"]

    assert client.delete("/nodes/2").status_code == 204
    assert [n["name"] for n in client.get("/nodes").json()] == ["A", "C"]
    assert client.get("/edges").json() == []
    assert client.delete("/nodes/2").status_code == 404


def test_create_edge():
    add_nodes("ServerA", "ServerB")
    r = client.post("/edges", json={"source": "ServerA", "destination": "ServerB", "latency": 12.5})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "source": "ServerA", "destination": "ServerB", "latency": 12.5}


@pytest.mark.parametrize(
    "body",
    [
        {"destination": "B", "latency": 1},
        {"source": "A", "latency": 1},
        {"source": "A", "destination": "B"},
        {"source": "A", "destination": "B", "latency": 0},
        {"source": "A", "destination": "B", "latency": -3},
        {"source": "A", "destination": "B", "latency": "5"},
        {"source": "A", "destination": "B", "latency": True},
        {"source": "A", "destination": "A", "latency": 1},
        {"source": "A", "destination": "Z", "latency": 1},
    ],
)
def test_create_edge_invalid(body):
    add_nodes("A", "B")
    r = client.post("/edges", json=body)
    assert r.status_code == 400, r.json()
    assert "error" in r.json()


def test_create_edge_duplicate():
    add_nodes("A", "B")
    add_edge("A", "B", 1)
    r = client.post("/edges", json={"source": "A", "destination": "B", "latency": 2})
    assert r.status_code == 400
    # opposite direction is a distinct edge
    add_edge("B", "A", 2)


def test_delete_edge():
    add_nodes("A", "B")
    add_edge("A", "B", 1)
    assert client.delete("/edges/1").status_code == 204
    assert client.get("/edges").json() == []
    assert client.delete("/edges/1").status_code == 404


def build_sample_network():
    add_nodes("ServerA", "ServerB", "ServerC", "ServerD", "ServerE")
    add_edge("ServerA", "ServerB", 10.0)
    add_edge("ServerB", "ServerD", 13.4)
    add_edge("ServerA", "ServerC", 5.0)
    add_edge("ServerC", "ServerD", 30.0)
    add_edge("ServerA", "ServerD", 50.0)


def test_shortest_route():
    build_sample_network()
    r = client.post("/routes/shortest", json={"source": "ServerA", "destination": "ServerD"})
    assert r.status_code == 200
    assert r.json() == {"total_latency": 23.4, "path": ["ServerA", "ServerB", "ServerD"]}


def test_shortest_route_no_path():
    build_sample_network()
    r = client.post("/routes/shortest", json={"source": "ServerA", "destination": "ServerE"})
    assert r.status_code == 404
    assert r.json() == {"error": "No path exists between ServerA and ServerE"}


def test_shortest_route_is_directed():
    build_sample_network()
    r = client.post("/routes/shortest", json={"source": "ServerD", "destination": "ServerA"})
    assert r.status_code == 404


def test_shortest_route_same_node():
    build_sample_network()
    r = client.post("/routes/shortest", json={"source": "ServerA", "destination": "ServerA"})
    assert r.json() == {"total_latency": 0.0, "path": ["ServerA"]}


@pytest.mark.parametrize(
    "body", [{}, {"source": "ServerA"}, {"source": "ServerA", "destination": "Nope"}, {"source": "", "destination": "ServerA"}]
)
def test_shortest_route_invalid(body):
    build_sample_network()
    r = client.post("/routes/shortest", json=body)
    assert r.status_code == 400
    assert "error" in r.json()


def test_dijkstra_prefers_more_hops_when_cheaper():
    g = build_graph([("A", "B", 1), ("B", "C", 1), ("C", "D", 1), ("A", "D", 10)])
    assert shortest_path(g, "A", "D") == (3, ["A", "B", "C", "D"])


def test_dijkstra_handles_cycles():
    g = build_graph([("A", "B", 1), ("B", "A", 1), ("B", "C", 2)])
    assert shortest_path(g, "A", "C") == (3, ["A", "B", "C"])
    assert shortest_path(g, "C", "A") is None


def test_history_records_and_filters():
    build_sample_network()
    client.post("/routes/shortest", json={"source": "ServerA", "destination": "ServerD"})
    client.post("/routes/shortest", json={"source": "ServerB", "destination": "ServerD"})
    client.post("/routes/shortest", json={"source": "ServerA", "destination": "ServerC"})
    client.post("/routes/shortest", json={"source": "ServerA", "destination": "ServerE"})  # no path -> not recorded

    history = client.get("/routes/history").json()
    assert len(history) == 3
    entry = history[-1]
    assert set(entry) == {"id", "source", "destination", "total_latency", "path", "created_at"}
    assert entry["path"] == ["ServerA", "ServerB", "ServerD"]
    assert entry["created_at"].endswith("Z")
    # most recent first
    assert [h["id"] for h in history] == [3, 2, 1]

    assert len(client.get("/routes/history", params={"source": "ServerA"}).json()) == 2
    assert len(client.get("/routes/history", params={"destination": "ServerD"}).json()) == 2
    assert len(client.get("/routes/history", params={"source": "ServerA", "destination": "ServerD"}).json()) == 1
    assert len(client.get("/routes/history", params={"limit": 1}).json()) == 1


def test_history_date_filters():
    build_sample_network()
    client.post("/routes/shortest", json={"source": "ServerA", "destination": "ServerD"})
    now = datetime.now(timezone.utc)
    past = (now - timedelta(hours=1)).isoformat()
    future = (now + timedelta(hours=1)).isoformat()

    assert len(client.get("/routes/history", params={"date_from": past}).json()) == 1
    assert len(client.get("/routes/history", params={"date_from": future}).json()) == 0
    assert len(client.get("/routes/history", params={"date_to": past}).json()) == 0
    assert len(client.get("/routes/history", params={"date_from": past, "date_to": future}).json()) == 1


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": "abc"}, {"date_from": "not-a-date"}, {"date_from": "2026-02-21", "date_to": "2026-02-20"}],
)
def test_history_invalid_params(params):
    r = client.get("/routes/history", params=params)
    assert r.status_code == 400
    assert "error" in r.json()


def teardown_module():
    engine.dispose()
    if os.path.exists("test_network.db"):
        os.remove("test_network.db")
