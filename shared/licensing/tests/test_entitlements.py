import shared.licensing.entitlements as ent


def test_flag_off_denies(monkeypatch):
    monkeypatch.setattr(ent, "_flag_on", lambda key, did: False)
    assert ent.feature_enabled("waddleperf_c2c", "region_matrix") is False


def test_flag_on_unlicensed_feature_allows(monkeypatch):
    monkeypatch.setattr(ent, "_flag_on", lambda key, did: True)
    assert ent.feature_enabled("sase", "firewall") is True


def test_licensed_feature_requires_entitlement(monkeypatch):
    monkeypatch.setattr(ent, "_flag_on", lambda key, did: True)
    monkeypatch.setattr(ent, "_licensed", lambda f: False)
    assert ent.feature_enabled("sase", "sso", licensed=True) is False
    monkeypatch.setattr(ent, "_licensed", lambda f: True)
    assert ent.feature_enabled("sase", "sso", licensed=True) is True
