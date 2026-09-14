from comms.python import protocol
from comms.python.serial_link import SerialLink


def test_feed_dispatches_handler():
    link = SerialLink(port="/dev/null")
    received = []
    link.on_message("tof_gnd", lambda msg: received.append(msg.int_value()))

    line = protocol.encode("tof_gnd", "500", 0)
    count = link.feed(line)

    assert count == 1
    assert received == [500]
    assert link.stats.messages_ok == 1


def test_feed_counts_checksum_drops_without_raising():
    link = SerialLink(port="/dev/null")
    count = link.feed(b"tof_gnd,812,104,00\n")
    assert count == 0
    assert link.stats.messages_dropped_checksum == 1


def test_heartbeat_marks_link_alive():
    link = SerialLink(port="/dev/null")
    assert link.stats.mcu_alive is False
    link.feed(protocol.encode("heartbeat", "12345", 0))
    assert link.stats.mcu_alive is True


def test_feed_processes_multiple_messages_and_tracks_gaps():
    link = SerialLink(port="/dev/null")
    link.feed(protocol.encode("us_l", "30", 0))
    link.feed(protocol.encode("us_l", "31", 2))  # gap of 1
    assert link.stats.gaps_by_tag["us_l"] == 1
