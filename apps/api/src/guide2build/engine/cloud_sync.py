"""Optional parent-process request sync; inference children never receive this identity."""
import time
import uuid
from ..catalog import find_set


def sync_requests(store, config, project="lumensparkxy", client=None):
    from google.cloud import firestore
    if client is None:
        from ..releases.auth import role_credentials
        client = firestore.Client(project=project, database="guide2build-requests",
                                  credentials=role_credentials(project, "uploader"))
    owner = uuid.uuid4().hex
    imported = 0
    for snapshot in client.collection("requests").where(filter=firestore.FieldFilter("status", "in", ["requested", "engine_claimed"])).limit(100).stream():
        document = snapshot.reference

        @firestore.transactional
        def claim(transaction):
            value = document.get(transaction=transaction).to_dict()
            if not value or value.get("status") not in {"requested", "engine_claimed"}:
                return None
            if value.get("engine_lease_until", 0) > time.time():
                return None
            set_number = value.get("set_number")
            if set_number != document.id or not isinstance(set_number, str):
                return None
            transaction.update(document, {"status": "engine_claimed", "engine_claim_owner": owner,
                                          "engine_lease_until": time.time()+120})
            return set_number

        set_number = claim(client.transaction())
        if set_number is None:
            continue
        try:
            entry = find_set(set_number)
            ids = [store.enqueue(set_number, guide["guide_id"], config)["id"] for guide in entry["guides"]]
            status = "queued"
        except (KeyError, ValueError):
            ids, status = [], "source_discovery_required"

        @firestore.transactional
        def finish(transaction):
            value = document.get(transaction=transaction).to_dict()
            if value and value.get("engine_claim_owner") == owner:
                transaction.update(document, {"status": status, "engine_job_ids": ids, "engine_lease_until": 0})

        finish(client.transaction())
        imported += 1
    return {"imported_requests": imported}


class RequestSyncLoop:
    """Poll while a long local job is running, without an always-on cloud worker."""
    def __init__(self, store, config, project, report):
        import threading
        self.stop = threading.Event()
        self.store, self.config, self.project, self.report = store, config, project, report
        self.thread = threading.Thread(target=self.run, name="guide2build-request-sync", daemon=True)

    def run(self):
        while not self.stop.is_set():
            try:
                self.report(sync_requests(self.store, self.config, self.project))
            except Exception as error:
                self.report({"cloud_sync": "unavailable", "error_type": type(error).__name__})
            self.stop.wait(300)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
