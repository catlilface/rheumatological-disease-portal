def staff_fixture(authority, email, password, role):
    """Disposable DB setup only. The portal assigns staff roles via authenticated SetRole."""
    with authority.transaction() as cur:
        authority.insert_account(cur, email, password, role)
