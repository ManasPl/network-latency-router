# Network Route Optimization API

REST API to add servers (nodes) and connections between them (edges) with latency, and find the shortest route between two servers.

Built with Python, FastAPI, SQLAlchemy and SQLite.

**Test case sheet:** [Google Sheet](https://docs.google.com/spreadsheets/d/1nB3-jVa17EKDzB4DhaVCn0ZFpeG1qlxXEA1b57c6KQE/edit?usp=sharing)

## How to run

You need Python 3.9 or newer.

**1. Clone the repo**

```bash
git clone <repo-url>
cd <repo-folder>
```

**2. Create a virtual environment and install dependencies**

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**3. Start the server**

```bash
uvicorn app.main:app --reload
```

**4. Try the APIs**

- Open http://127.0.0.1:8000/docs in a browser. Click any endpoint, then **Try it out** → **Execute**.
- Or use the curl commands in the example below.

Data is stored in `network.db` (SQLite). It is created automatically, and you can delete it to start fresh. You can change the database with the `DATABASE_URL` env variable.

## Running tests

With the virtual environment activated:

```bash
pytest
```

The tests use a separate temporary database, so they don't touch `network.db`.

The manual test cases (input, expected result, actual result) are in the [test case sheet](https://docs.google.com/spreadsheets/d/1nB3-jVa17EKDzB4DhaVCn0ZFpeG1qlxXEA1b57c6KQE/edit?usp=sharing).

## APIs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /nodes | Add a node |
| POST | /edges | Add an edge between two nodes |
| POST | /routes/shortest | Get shortest route between two nodes |
| GET | /routes/history | Get past route queries (filters: source, destination, limit, date_from, date_to) |
| GET | /nodes | List nodes |
| GET | /edges | List edges |
| DELETE | /nodes/{id} | Delete a node |
| DELETE | /edges/{id} | Delete an edge |

Errors are returned as `{"error": "message"}` with status 400 for invalid input and 404 when no path is found or the id does not exist.

Example:

```bash
curl -X POST localhost:8000/nodes -H "Content-Type: application/json" -d '{"name": "ServerA"}'
curl -X POST localhost:8000/nodes -H "Content-Type: application/json" -d '{"name": "ServerB"}'
curl -X POST localhost:8000/edges -H "Content-Type: application/json" -d '{"source": "ServerA", "destination": "ServerB", "latency": 12.5}'
curl -X POST localhost:8000/routes/shortest -H "Content-Type: application/json" -d '{"source": "ServerA", "destination": "ServerB"}'
curl "localhost:8000/routes/history?source=ServerA&limit=10"
```

## Assumptions

- Edges are one directional. ServerA to ServerB and ServerB to ServerA are two different edges.
- An edge from a node to itself is not allowed.
- Shortest route is calculated using Dijkstra's algorithm since all latencies are positive.
- If source and destination are the same, total_latency is 0 and the path has only that node.
- Only successful route queries are saved in history. History is sorted with the latest first.
- Deleting a node also deletes all its edges. Route history is not affected.
- Dates in history filters are in ISO format, e.g. 2026-02-20T14:32:00Z, and are treated as UTC.
