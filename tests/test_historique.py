import json
import types

from pipeline import historique


class FakeSB:
    def __init__(self, empty=None):
        self.files, self.empty = {}, empty
        self.storage = types.SimpleNamespace(from_=lambda b: types.SimpleNamespace(upload=lambda p, body, o: self.files.__setitem__(p, json.loads(body))))

    def rpc(self, name, args):
        data = {"version": "v2026.20.0", "released_at": "2026-11-09T07:04:09Z"} if name == "historique_source" else ([] if name == self.empty else [{"x": 1}])
        return types.SimpleNamespace(execute=lambda: types.SimpleNamespace(data=data))


def test_publishes_every_statistic_with_its_source():
    sb = FakeSB()
    sizes = historique.build(sb, "web")
    assert set(sizes) == set(historique.NAMES)
    doc = sb.files["historique/grid.json"]
    assert doc["data"] == [{"x": 1}] and doc["source"].startswith("F1DB v2026.20.0")


def test_an_empty_statistic_fails_the_run():
    try:
        historique.build(FakeSB(empty="historique_eras"), "web")
    except RuntimeError as e:
        assert "historique_eras" in str(e)
    else:
        raise AssertionError("an empty statistic must not be published")
