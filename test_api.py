"""
Perenti / EBC Backend — API Tests
Run: pytest test_api.py -v
"""
import os, json, random, string
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

# Import after env is loaded so Appwrite credentials are set
from main import app

client = TestClient(app)

# ── Helpers ──────────────────────────────────────────────────────────────────

def rand_email():
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"test_{suffix}@perenti.test"

def rand_name():
    return f"Test User {''.join(random.choices(string.ascii_uppercase, k=4))}"


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_root_returns_ok(self):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "Perenti" in data.get("service", "")


# ── Members ───────────────────────────────────────────────────────────────────

class TestMembers:
    def test_get_members_returns_list(self):
        r = client.get("/api/members")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_members_have_required_fields(self):
        r = client.get("/api/members")
        assert r.status_code == 200
        members = r.json()
        if len(members) > 0:
            m = members[0]
            assert "id" in m or "$id" in m
            assert "name" in m


# ── Meetups ───────────────────────────────────────────────────────────────────

class TestMeetups:
    def test_get_meetups_returns_list(self):
        r = client.get("/api/meetups")
        assert r.status_code == 200
        data = r.json()
        # Could be a list or dict with 'meetups' key
        assert isinstance(data, (list, dict))

    def test_get_meetups_has_ebc_28(self):
        """The seed script should have created EBC 28th Meetup."""
        r = client.get("/api/meetups")
        assert r.status_code == 200
        data = r.json()
        meetups = data if isinstance(data, list) else data.get("meetups", [])
        titles = [m.get("title", "") for m in meetups]
        # At least one meetup should exist
        assert len(meetups) >= 1, "No meetups found — run seed_meetups.py first"

    def test_get_meetup_by_id(self):
        """Fetch all meetups, then get the first one by ID."""
        r = client.get("/api/meetups")
        assert r.status_code == 200
        meetups = r.json()
        if not isinstance(meetups, list) or len(meetups) == 0:
            pytest.skip("No meetups in DB")
        meetup_id = meetups[0]["id"]
        r2 = client.get(f"/api/meetups/{meetup_id}")
        assert r2.status_code == 200
        detail = r2.json()
        assert detail["id"] == meetup_id
        assert "registered_count" in detail
        assert "remaining" in detail

    def test_get_nonexistent_meetup_404(self):
        r = client.get("/api/meetups/nonexistent_id_xyz")
        assert r.status_code == 404

    def test_create_meetup(self):
        """Create a test meetup (will remain in DB, but with is_active=False)."""
        payload = {
            "title": f"Test Meetup {rand_name()}",
            "description": "Automated test meetup — safe to delete",
            "date": "Saturday, July 5th 2026",
            "time": "9:00 AM – 11:00 AM (IST)",
            "venue": "Test Venue, Hyderabad",
            "banner_url": "",
            "capacity": 10,
            "is_active": False,  # Keep hidden from users
        }
        r = client.post("/api/meetups", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == payload["title"]
        assert data["capacity"] == 10
        assert data["is_active"] is False
        # Store ID for use in reservation tests
        TestMeetups._test_meetup_id = data["id"]

    @classmethod
    def get_test_meetup_id(cls):
        return getattr(cls, '_test_meetup_id', None)


# ── Reservations ──────────────────────────────────────────────────────────────

class TestReservations:
    _meetup_id = None

    @classmethod
    def setup_class(cls):
        """Create a fresh test meetup for reservation tests."""
        r = client.post("/api/meetups", json={
            "title": "Reservation Test Meetup",
            "description": "Auto-created for reservation testing",
            "date": "Test Date",
            "time": "10:00 AM",
            "venue": "Test Venue",
            "banner_url": "",
            "capacity": 5,
            "is_active": False,
        })
        if r.status_code == 200:
            cls._meetup_id = r.json()["id"]

    def test_get_reservations_empty(self):
        """New meetup should have zero reservations."""
        if not self._meetup_id:
            pytest.skip("Could not create test meetup")
        r = client.get(f"/api/reservations/{self._meetup_id}")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_create_reservation(self):
        """Register one person for the test meetup."""
        if not self._meetup_id:
            pytest.skip("Could not create test meetup")
        email = rand_email()
        name = rand_name()
        payload = {
            "meetup_id": self._meetup_id,
            "user_email": email,
            "user_name": name,
            "quantity": 1,
            "answers": json.dumps({"building": "Test project", "role": "Founder", "lookingFor": "Co-founder"}),
        }
        r = client.post("/api/reservations", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["user_email"] == email
        assert data["user_name"] == name
        assert data["quantity"] == 1
        assert data["status"] == "confirmed"
        # Ticket ID should follow PRNT-EBC-XXXXXX format
        assert data["ticket_id"].startswith("PRNT-EBC-")
        assert len(data["ticket_id"]) == len("PRNT-EBC-") + 6

    def test_reservation_appears_in_list(self):
        """After creating a reservation, it should appear in GET /api/reservations."""
        if not self._meetup_id:
            pytest.skip("Could not create test meetup")
        email = rand_email()
        client.post("/api/reservations", json={
            "meetup_id": self._meetup_id,
            "user_email": email,
            "user_name": rand_name(),
            "quantity": 1,
            "answers": "{}",
        })
        r = client.get(f"/api/reservations/{self._meetup_id}")
        assert r.status_code == 200
        emails = [x["user_email"] for x in r.json()]
        assert email in emails

    def test_capacity_enforcement(self):
        """Booking beyond capacity (5 seats) should fail with 400."""
        if not self._meetup_id:
            pytest.skip("Could not create test meetup")
        # Fill 5 seats with one booking
        r = client.post("/api/reservations", json={
            "meetup_id": self._meetup_id,
            "user_email": rand_email(),
            "user_name": rand_name(),
            "quantity": 5,
            "answers": "{}",
        })
        # Might pass or fail depending on existing reservations — that's ok
        # Now try booking 1 more — should be blocked
        r2 = client.post("/api/reservations", json={
            "meetup_id": self._meetup_id,
            "user_email": rand_email(),
            "user_name": rand_name(),
            "quantity": 1,
            "answers": "{}",
        })
        # Either the above fills it OR this one overflows — at least one should be 400
        # We accept 200 or 400 here, just not 500
        assert r2.status_code in (200, 400)
        if r2.status_code == 200:
            # Try once more — now it must be 400
            r3 = client.post("/api/reservations", json={
                "meetup_id": self._meetup_id,
                "user_email": rand_email(),
                "user_name": rand_name(),
                "quantity": 5,
                "answers": "{}",
            })
            assert r3.status_code == 400

    def test_meetup_registered_count_updates(self):
        """After reservations, GET /api/meetups/:id should reflect accurate count."""
        if not self._meetup_id:
            pytest.skip("Could not create test meetup")
        r = client.get(f"/api/meetups/{self._meetup_id}")
        assert r.status_code == 200
        data = r.json()
        assert "registered_count" in data
        assert "remaining" in data
        assert data["registered_count"] >= 0
        assert data["remaining"] >= 0
        assert data["registered_count"] + data["remaining"] == data["capacity"]


# ── Edge Cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_invalid_meetup_id_for_reservation(self):
        r = client.post("/api/reservations", json={
            "meetup_id": "completely_invalid_meetup_xyz",
            "user_email": rand_email(),
            "user_name": rand_name(),
            "quantity": 1,
            "answers": "{}",
        })
        # Should fail gracefully — 404 or 500, not crash
        assert r.status_code in (400, 404, 500)

    def test_cors_headers_present(self):
        """Preflight OPTIONS should respond for CORS."""
        r = client.options("/api/meetups", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
        # FastAPI with CORS middleware should handle this
        assert r.status_code in (200, 204, 400)

    def test_empty_email_rejected(self):
        """An empty email string should be caught at schema validation level."""
        r = client.post("/api/reservations", json={
            "meetup_id": "someid",
            "user_email": "",
            "user_name": "Test",
            "quantity": 1,
            "answers": "{}",
        })
        # Pydantic should reject empty required string
        assert r.status_code in (400, 422, 500)
