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


def test_one_global_counter_across_interleaved_tags_is_not_a_gap():
    # The ESP32 numbers every line it sends with one counter, whatever the tag.
    link = SerialLink(port="/dev/null")
    for seq, (tag, value) in enumerate([("tof_fwd", "900"), ("us_l", "30"), ("grip", "3"), ("heartbeat", "1"), ("tof_fwd", "905")]):
        link.feed(protocol.encode(tag, value, seq))
    assert sum(link.stats.gaps_by_tag.values()) == 0


def test_dropped_message_in_interleaved_stream_is_counted_once():
    link = SerialLink(port="/dev/null")
    link.feed(protocol.encode("tof_fwd", "900", 0))
    link.feed(protocol.encode("us_l", "30", 1))
    link.feed(protocol.encode("grip", "3", 3))  # seq 2 was lost
    assert sum(link.stats.gaps_by_tag.values()) == 1
