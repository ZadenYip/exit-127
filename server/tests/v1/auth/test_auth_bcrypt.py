from v1.auth.bcrypt import hash_password, verify_password


def test_hash_password_can_be_verified() -> None:
    password = "correct-horse-battery"

    password_hash = hash_password(password)

    assert password_hash != password
    assert len(password_hash) == 60
    assert verify_password(password, password_hash)
    assert not verify_password("incorrect-password", password_hash)


def test_hash_password_uses_a_new_salt_each_time() -> None:
    password = "correct-horse-battery"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash)
    assert verify_password(password, second_hash)
