            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=self.settings.timeout_seconds,
                    transport=self.transport,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "POST",
                        "https://api.tavily.com/" + operation,
                        headers={
                            "Authorization": "Bearer " + self.settings.api_key.get_secret_value()
                        },
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            status = response.status_code
                            reason = (
                                "unauthorized"
                                if status in (401, 403)
                                else "rate_limited"
                                if status == 429
                                else "quota_exhausted"
                                if status in (402, 432, 433)
                                else "provider_error"
                            )
                            raise SearchError(reason)
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > self.settings.max_response_bytes:
                                raise SearchError("response_too_large")
                        import json

                        body = json.loads(data)
        except (httpx.TimeoutException, TimeoutError):
            raise SearchError("timeout") from None
        except httpx.HTTPError:
            raise SearchError("provider_error") from None
        except (ValueError, UnicodeError):
            raise SearchError("invalid_response") from None
        if not isinstance(body, dict):
            raise SearchError("invalid_response")
        budget.settle(_credits(body))
        return body

    def _sources(
        self,
        body: dict[str, object],
        content_key: str,
        scope: Literal["search_snippet", "extracted_page"],
        domains: tuple[str, ...],
        requested: set[str] | None,
    ) -> tuple[tuple[WebSource, ...], tuple[str, ...]]:
        rows = body.get("results")
        if not isinstance(rows, list):
            raise SearchError("invalid_response")
        found: list[WebSource] = []
        limitations: list[str] = []
        for row in rows[: self.settings.max_results if requested is None else 5]:
            if not isinstance(row, dict):
                raise SearchError("invalid_response")
            try:
                url = checked_source_url(row.get("url"), domains)
            except SearchError:
                limitations.append("out_of_scope_result")
                continue
            if requested is not None and url not in requested:
                limitations.append("unexpected_result")
                continue
            content = row.get(content_key)
            if not isinstance(content, str) or not content.strip():
                limitations.append("empty_content")
                continue
            truncated = len(content) > self.settings.max_content_chars
            content = content[: self.settings.max_content_chars]
            found.append(
                WebSource(
                    url,
                    row.get("title") if isinstance(row.get("title"), str) else None,
                    content,
                    scope,
                    datetime.now(UTC).isoformat(),
                    hashlib.sha256(content.encode()).hexdigest(),
                    row.get("published_date")
                    if isinstance(row.get("published_date"), str)
                    else None,
                    ("content_truncated",) if truncated else (),
                )
            )
        return tuple(found), tuple(dict.fromkeys(limitations))


def _credits(body: dict[str, object]) -> int | None:
    usage = body.get("usage")
    value = usage.get("credits") if isinstance(usage, dict) else None
    return value if type(value) is int and value >= 0 else None
