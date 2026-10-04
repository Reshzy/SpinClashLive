from color_rush.application.auth import bootstrap_owner
from color_rush.composition import build_container
from color_rush.domain.clock import utc_now
from color_rush.infrastructure.persistence.db import session_scope


def main() -> None:
    container = build_container()
    with session_scope(container.session_factory) as session:
        user = bootstrap_owner(session, container.settings, utc_now())
        print(f"owner ready: {user.username} ({user.role})")


if __name__ == "__main__":
    main()
