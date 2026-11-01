from _helpers import make_client, make_ctx


def test_websocket_receives_published_events(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c, c.websocket_connect("/ws/events") as ws:
        ctx.bus.publish("stage.changed", {"project_id": "p", "stage": "DRAFT"})
        assert ws.receive_json() == {
            "type": "stage.changed",
            "data": {"project_id": "p", "stage": "DRAFT"},
        }
    ctx.close()
