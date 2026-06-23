from veille_marches.state import FileStateStore, State


def test_idempotency_logic():
    st = State(posted_ids=["A"])
    assert st.is_new("A") is False
    assert st.is_new("B") is True


def test_file_store_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    store = FileStateStore(str(p))
    st = store.load()
    assert st.posted_ids == []
    st.mark_seen("REF1")
    st.mark_posted("REF1")
    st.finalize()
    store.save(st)

    st2 = store.load()
    assert st2.posted_ids == ["REF1"]
    assert "REF1" in st2.seen_ids
    assert st2.last_run is not None


def test_posted_never_removed():
    st = State(posted_ids=["OLD"])
    st.finalize()
    assert "OLD" in st.posted_ids


def test_seen_bounded():
    st = State(seen_ids=[str(i) for i in range(3000)])
    st.finalize()
    assert len(st.seen_ids) == 2000
