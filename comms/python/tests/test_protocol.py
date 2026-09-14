import pytest

from comms.python import protocol


def test_encode_decode_roundtrip():
    line = protocol.encode("tof_gnd", "812", 104)
    msg = protocol.decode(line)
    assert msg.tag == "tof_gnd"
    assert msg.value == "812"
    assert msg.int_value() == 812
    assert msg.seq == 104


def test_checksum_matches_documented_example():
    # PROTOCOL.md example line: tof_gnd,812,104,41
    line = protocol.encode("tof_gnd", "812", 104)
    assert line == b"tof_gnd,812,104,41\n"


def test_multi_field_value():
    line = protocol.encode("imu", "120|-45|1023", 7)
    msg = protocol.decode(line)
    assert msg.fields() == ["120", "-45", "1023"]


def test_checksum_mismatch_raises():
    with pytest.raises(protocol.ChecksumError):
        protocol.decode(b"tof_gnd,812,104,00\n")


def test_malformed_line_wrong_field_count():
    with pytest.raises(protocol.MalformedLineError):
        protocol.decode(b"tof_gnd,812\n")


def test_malformed_line_empty_field():
    with pytest.raises(protocol.MalformedLineError):
        protocol.decode(b",812,104,4F\n")


def test_malformed_line_non_integer_seq():
    with pytest.raises(protocol.MalformedLineError):
        protocol.decode(b"tof_gnd,812,abc,4F\n")


def test_encode_rejects_oversized_line():
    with pytest.raises(ValueError):
        protocol.encode("tag", "x" * 100, 1)


def test_line_assembler_handles_split_message():
    asm = protocol.LineAssembler()
    assert asm.feed(b"tof_gnd,812,") == []
    lines = asm.feed(b"104,4F\n")
    assert lines == [b"tof_gnd,812,104,4F\n"]


def test_line_assembler_handles_multiple_lines_in_one_read():
    asm = protocol.LineAssembler()
    lines = asm.feed(b"a,1,0,00\nb,2,1,00\n")
    assert len(lines) == 2


def test_line_assembler_drops_oversized_unterminated_buffer():
    asm = protocol.LineAssembler()
    asm.feed(b"x" * (protocol.MAX_LINE_LEN + 1))
    # buffer should have been cleared; next valid line still parses
    lines = asm.feed(b"tof_gnd,812,104,4F\n")
    assert lines == [b"tof_gnd,812,104,4F\n"]


def test_sequence_tracker_no_gap():
    tracker = protocol.SequenceTracker()
    msg0 = protocol.decode(protocol.encode("hb", "1", 0))
    msg1 = protocol.decode(protocol.encode("hb", "2", 1))
    assert tracker.observe(msg0) is None
    assert tracker.observe(msg1) == 0


def test_sequence_tracker_detects_gap():
    tracker = protocol.SequenceTracker()
    tracker.observe(protocol.decode(protocol.encode("hb", "1", 0)))
    gap = tracker.observe(protocol.decode(protocol.encode("hb", "2", 5)))
    assert gap == 4
    assert tracker.gaps_by_tag["hb"] == 4


def test_sequence_tracker_handles_wraparound():
    tracker = protocol.SequenceTracker()
    tracker.observe(protocol.decode(protocol.encode("hb", "1", 65535)))
    gap = tracker.observe(protocol.decode(protocol.encode("hb", "2", 0)))
    assert gap == 0
