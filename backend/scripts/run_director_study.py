def main() -> int:
    args = parser().parse_args()
    try:
        result = asyncio.run(execute(args))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_code": type(error).__name__}))
        return 1
    print(json.dumps({"status": "completed", "output": str(args.output)}, ensure_ascii=False))
    return technical_exit_code(result) if "cases" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
