"""
Print today's pattern (words + hidden rule). Run: python -m daily_game.daily
"""
from .generator import generate_daily


def main() -> None:
    result = generate_daily()
    if result is None:
        print("No pattern selected (try lowering MIN_PQS or rebuilding features).")
        return
    print("Today's words:")
    for w in result["words"]:
        print(f"  {w}")
    print()
    print("Hidden rule (for answer key):")
    print(f"  {result['rule']}")
    print(f"  (template={result['template_id']}, PQS={result['pqs']})")


if __name__ == "__main__":
    main()
