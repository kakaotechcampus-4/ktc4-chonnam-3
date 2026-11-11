def main() -> int:
    args = parser().parse_args()
    try:
        result = asyncio.run(execute(args))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_code": type(error).__name__}))
        return 1
    state = result["trajectory"]
    print(
        json.dumps(
            {"status": state["status"], "turns": len(state["turns"]), "output": str(args.output)}
        )
    )
    return 0 if state["status"] in {"awaiting_answer", "completed", "validated_only"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
