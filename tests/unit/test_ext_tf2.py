from steam.ext import tf2

client = tf2.Client()


def test_tf2_currencies():
    assert tf2.Metal(1.11) + tf2.Metal(1) == tf2.Metal(2.11)
    assert tf2.Metal(1.115)
