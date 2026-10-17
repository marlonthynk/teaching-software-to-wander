"""The viewer's endpoints: proposing, reviewing and applying, and other processes picking it up."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from wander import core, tools
from wander.ontology import Ontology
from wander.viewer.server import make_handler


@pytest.fixture
def viewer(ontology_file):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tools.Context("memory")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def post(base, path, body, headers=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(base, path):
    with urllib.request.urlopen(base + path) as res:
        return res.read()


REFERRED_BY = {"kind": "relationship", "name": "REFERRED_BY", "from": "Customer", "to": "Partner",
               "description": "The partner that referred this customer.", "proposed_by": "Tom"}
PARTNER = {"kind": "entity", "name": "Partner", "description": "A firm that refers customers to us.",
           "properties": {"notes": "What we've agreed."}, "proposed_by": "Tom"}


def test_proposals_wait_for_review(viewer, ontology_file):
    status, body = post(viewer, "/propose", PARTNER)
    assert status == 200 and body["status"] == "pending review" and body["would_load"] == 2
    status, body = post(viewer, "/propose", REFERRED_BY)
    assert status == 200 and body["would_load"] == 12
    onto = Ontology.load(ontology_file)
    assert "Partner" not in onto.entities and len(onto.proposals) == 2
    drawn = json.loads(get(viewer, "/ontology.json"))
    assert [p["name"] for p in drawn["proposals"]] == ["Partner", "REFERRED_BY"]
    review = json.loads(get(viewer, "/proposals.json"))
    assert [(p["id"], p["valid"], p["would_load"]) for p in review["pending"]] == [("p1", True, 2), ("p2", True, 12)]


def test_a_developer_applies_them(viewer, ontology_file):
    chat = tools.Context("memory")  # stands in for the chat app, opened before any change
    overdue = [n["id"] for n in core.find(chat.graph, "Customer", {"payment_status": "overdue"})["nodes"]]
    post(viewer, "/propose", PARTNER)
    post(viewer, "/propose", REFERRED_BY)
    assert core.wander(chat.graph, overdue)["convergence"] == []  # proposed, not applied

    status, body = post(viewer, "/apply", {"ids": ["p2"], "reviewed_by": "Marlon"})
    assert status == 400 and "apply that one too" in body["error"]
    status, body = post(viewer, "/apply", {"ids": ["p1", "p2"], "reviewed_by": "Marlon"})
    assert status == 200 and [a["loaded"] for a in body["applied"]] == [2, 12]

    onto = Ontology.load(ontology_file)
    assert "REFERRED_BY" in onto.relationships and not onto.proposals
    assert onto.changelog[-1]["by"] == "Tom" and onto.changelog[-1]["reviewed_by"] == "Marlon"
    assert core.wander(chat.graph, overdue)["convergence"][0]["name"] == "Northwind Consulting"


def test_a_developer_rejects_one(viewer, ontology_file):
    post(viewer, "/propose", PARTNER)
    status, body = post(viewer, "/reject", {"id": "p1", "reviewed_by": "Marlon", "reason": "Not yet."})
    assert status == 200
    review = json.loads(get(viewer, "/proposals.json"))
    assert review["pending"] == [] and review["rejected"][0]["reason"] == "Not yet."


def test_validation_errors_come_back_readable(viewer, ontology_file):
    before = ontology_file.read_text()
    status, body = post(viewer, "/propose", REFERRED_BY)  # Partner isn't declared or proposed
    assert status == 400 and "Declare it first" in body["error"]
    assert ontology_file.read_text() == before


def test_refuses_other_sites_and_non_json(viewer, ontology_file):
    for path in ("/propose", "/apply", "/reject"):
        status, _ = post(viewer, path, PARTNER, headers={"Origin": "https://evil.example"})
        assert status == 403
    req = urllib.request.Request(viewer + "/propose", data=b"kind=entity", method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 415
    assert not Ontology.load(ontology_file).proposals


def test_serves_both_pages(viewer):
    assert b"Add knowledge" in get(viewer, "/")
    assert b"Review proposed changes" in get(viewer, "/review")
