# API Examples

All FMS models are exposed via NetBox's REST API at `/api/plugins/fms/`. The browsable
API is available at that URL in a browser. GraphQL queries are available at `/graphql/`.

## Authentication

Authenticate with a NetBox API token by including an `Authorization` header:

```
Authorization: Token <your-token>
```

All examples below use the following variables:

```python
NETBOX_URL = "https://netbox.example.com"
TOKEN = "your-api-token-here"
```

---

## 1. List Fiber Cable Types

Retrieve all fiber cable types.

**Request**

```
GET /api/plugins/fms/cable-types/
```

**curl**

```bash
curl -s -H "Authorization: Token $TOKEN" \
  "$NETBOX_URL/api/plugins/fms/cable-types/" | python3 -m json.tool
```

**Python**

```python
import requests

headers = {"Authorization": f"Token {TOKEN}"}
response = requests.get(f"{NETBOX_URL}/api/plugins/fms/cable-types/", headers=headers)
cable_types = response.json()

for ct in cable_types["results"]:
    print(f"{ct['id']}: {ct['manufacturer']['display']} {ct['model']} "
          f"({ct['construction']}, {ct['fiber_type']}, {ct['strand_count']}f)")
```

**Sample response**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "url": "https://netbox.example.com/api/plugins/fms/cable-types/1/",
      "display": "Corning ALTOS 048EUC-T4101D20",
      "manufacturer": {
        "id": 5,
        "url": "https://netbox.example.com/api/dcim/manufacturers/5/",
        "display": "Corning"
      },
      "model": "ALTOS 048EUC-T4101D20",
      "construction": "loose_tube",
      "fiber_type": "smf_os2",
      "strand_count": 48,
      "instance_count": 3,
      "tags": []
    }
  ]
}
```

---

## 2. Create a Fiber Cable Type

Create a new fiber cable type blueprint.

**Request**

```
POST /api/plugins/fms/cable-types/
```

**curl**

```bash
curl -s -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "manufacturer": 5,
    "model": "ALTOS 096EUC-T4101D20",
    "construction": "loose_tube",
    "fiber_type": "smf_os2",
    "strand_count": 96
  }' \
  "$NETBOX_URL/api/plugins/fms/cable-types/"
```

**Python**

```python
import requests

headers = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
}
data = {
    "manufacturer": 5,
    "model": "ALTOS 096EUC-T4101D20",
    "construction": "loose_tube",
    "fiber_type": "smf_os2",
    "strand_count": 96,
}
response = requests.post(
    f"{NETBOX_URL}/api/plugins/fms/cable-types/",
    headers=headers,
    json=data,
)
print(response.status_code)  # 201
print(response.json()["id"])
```

Valid values for `construction`: `loose_tube`, `tight_buffer`, `ribbon`, `ribbon_in_tube`,
`micro`, `blown_fiber`.

Valid values for `fiber_type`: `smf_os1`, `smf_os2`, `mmf_om1`, `mmf_om2`, `mmf_om3`,
`mmf_om4`, `mmf_om5`.

---

## 3. Create a Fiber Cable

Create a fiber cable instance linked to an existing `dcim.Cable` and a fiber cable type.
On creation, internal components (buffer tubes, fiber strands, cable elements) are
automatically instantiated from the type's templates.

**Request**

```
POST /api/plugins/fms/fiber-cables/
```

**curl**

```bash
curl -s -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "fiber_cable_type": 1,
    "cable": 42
  }' \
  "$NETBOX_URL/api/plugins/fms/fiber-cables/"
```

**Python**

```python
import requests

headers = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
}
data = {
    "fiber_cable_type": 1,
    "cable": 42,
}
response = requests.post(
    f"{NETBOX_URL}/api/plugins/fms/fiber-cables/",
    headers=headers,
    json=data,
)
fiber_cable = response.json()
print(f"Created FiberCable {fiber_cable['id']} with type {fiber_cable['fiber_cable_type']['display']}")
```

> **Note:** Creating a fiber cable automatically instantiates all internal components
> (buffer tubes, ribbons, fiber strands, cable elements) based on the linked fiber cable
> type's templates. You do not need to create these individually.

---

## 4. List Fiber Strands for a Cable

Retrieve all fiber strands belonging to a specific fiber cable by filtering on
`fiber_cable_id`.

**Request**

```
GET /api/plugins/fms/fiber-strands/?fiber_cable_id=1
```

**curl**

```bash
curl -s -H "Authorization: Token $TOKEN" \
  "$NETBOX_URL/api/plugins/fms/fiber-strands/?fiber_cable_id=1" | python3 -m json.tool
```

**Python**

```python
import requests

headers = {"Authorization": f"Token {TOKEN}"}
params = {"fiber_cable_id": 1}
response = requests.get(
    f"{NETBOX_URL}/api/plugins/fms/fiber-strands/",
    headers=headers,
    params=params,
)
strands = response.json()

for s in strands["results"]:
    tube = s["buffer_tube"]["display"] if s["buffer_tube"] else "none"
    print(f"  Strand {s['position']}: color={s['color']}, tube={tube}")
```

**Sample response**

```json
{
  "count": 48,
  "next": "https://netbox.example.com/api/plugins/fms/fiber-strands/?fiber_cable_id=1&limit=50&offset=50",
  "previous": null,
  "results": [
    {
      "id": 1,
      "url": "https://netbox.example.com/api/plugins/fms/fiber-strands/1/",
      "display": "Strand 1",
      "fiber_cable": 1,
      "buffer_tube": 1,
      "ribbon": null,
      "name": "Strand 1",
      "position": 1,
      "color": "bl",
      "front_port_a": null,
      "front_port_b": null,
      "tags": []
    }
  ]
}
```

You can also filter by `buffer_tube_id` or `ribbon_id` to narrow results further.

---

## 5. Create a Splice Plan Entry

Add a splice mapping between two FrontPorts within an existing splice plan. Each entry
connects fiber A to fiber B through a tray (module).

**Request**

```
POST /api/plugins/fms/splice-plan-entries/
```

**curl**

```bash
curl -s -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan": 1,
    "tray": 10,
    "fiber_a": 101,
    "fiber_b": 202
  }' \
  "$NETBOX_URL/api/plugins/fms/splice-plan-entries/"
```

**Python**

```python
import requests

headers = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
}
data = {
    "plan": 1,
    "tray": 10,
    "fiber_a": 101,
    "fiber_b": 202,
}
response = requests.post(
    f"{NETBOX_URL}/api/plugins/fms/splice-plan-entries/",
    headers=headers,
    json=data,
)
entry = response.json()
print(f"Splice entry {entry['id']}: {entry['fiber_a']['display']} <-> {entry['fiber_b']['display']}")
```

The `plan` field is the splice plan ID. The `tray` field is the module (tray) ID on the
closure device. `fiber_a` and `fiber_b` are FrontPort IDs representing the fiber
endpoints being spliced.

---

## 6. List Fiber Circuits with Status Filter

Retrieve fiber circuits filtered by status.

**Request**

```
GET /api/plugins/fms/fiber-circuits/?status=active
```

**curl**

```bash
curl -s -H "Authorization: Token $TOKEN" \
  "$NETBOX_URL/api/plugins/fms/fiber-circuits/?status=active" | python3 -m json.tool
```

**Python**

```python
import requests

headers = {"Authorization": f"Token {TOKEN}"}
params = {"status": "active"}
response = requests.get(
    f"{NETBOX_URL}/api/plugins/fms/fiber-circuits/",
    headers=headers,
    params=params,
)
circuits = response.json()

for c in circuits["results"]:
    print(f"{c['id']}: {c['name']} (CID: {c['cid']}, status: {c['status']}, "
          f"strands: {c['strand_count']})")
```

**Sample response**

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "url": "https://netbox.example.com/api/plugins/fms/fiber-circuits/1/",
      "display": "CIRCUIT-001",
      "name": "CIRCUIT-001",
      "cid": "FBR-2025-0042",
      "status": "active",
      "description": "Main backbone circuit between Site A and Site B",
      "strand_count": 2,
      "tenant": null,
      "tags": []
    },
    {
      "id": 2,
      "url": "https://netbox.example.com/api/plugins/fms/fiber-circuits/2/",
      "display": "CIRCUIT-002",
      "name": "CIRCUIT-002",
      "cid": "FBR-2025-0043",
      "status": "active",
      "description": "Redundant path for CIRCUIT-001",
      "strand_count": 2,
      "tenant": null,
      "tags": []
    }
  ]
}
```

Valid values for `status`: `planned`, `staged`, `active`, `decommissioned`.
