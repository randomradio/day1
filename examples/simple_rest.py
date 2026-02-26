"""Example: use the Day1 REST SDK placeholder."""

from __future__ import annotations

from day1.sdk import Day1Client


def main() -> None:
    with Day1Client() as client:
        print("health:", client.health())
        fact = client.write_fact(
            "Day1 SDK placeholder installed",
            category="integration",
            session_id="sdk-example",
        )
        print("fact:", fact)
        print("search:", client.search("SDK placeholder", limit=5))
        print("related:", client.get_fact_related(fact["id"]))


if __name__ == "__main__":
    main()

