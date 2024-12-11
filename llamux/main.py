import time
import os
import hashlib
import litellm

CACHE_DIR = os.path.expanduser("~/.cache/llamux")


class QuotaManager:
    def __init__(
        self,
        id: str,
        tpm: int | None = None,
        rpm: int | None = None,
        tph: int | None = None,
        rph: int | None = None,
        tpd: int | None = None,
        rpd: int | None = None,
    ):
        self.file: str = os.path.join(CACHE_DIR, id)
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        if not os.path.exists(self.file):
            self.write([])  # init cache file.
        self.tpm: int | None = tpm  # tokens per minute
        self.rpm: int | None = rpm  # requests per minute
        self.tph: int | None = tph  # tokens per hour
        self.rph: int | None = rph  # requests per hour
        self.tpd: int | None = tpd  # tokens per day
        self.rpd: int | None = rpd  # requests per day
        self.id: str = id

    def available(self, tokens: int) -> bool:
        lines: list[str] = self.sync()
        now = int(time.time())
        conditions: list[bool] = []

        if self.rpd is not None:
            last_day_requests = len(lines)
            conditions.append(last_day_requests < self.rpd)

        if self.tpd is not None:
            last_day_tokens = sum(int(e.split(",")[1]) for e in lines)
            conditions.append(last_day_tokens + tokens < self.tpd)

        if self.rph is not None or self.tph is not None:
            last_hour_lines = [
                e for e in lines if int(float(e.split(",")[0])) >= now - 3600
            ]

            if self.rph is not None:
                last_hour_requests = len(last_hour_lines)
                conditions.append(last_hour_requests < self.rph)

            if self.tph is not None:
                last_hour_tokens = sum(int(e.split(",")[1]) for e in last_hour_lines)
                conditions.append(last_hour_tokens + tokens < self.tph)

        if self.rpm is not None or self.tpm is not None:
            last_minute_lines = [
                e for e in lines if int(float(e.split(",")[0])) >= now - 60
            ]

            if self.rpm is not None:
                last_minute_requests = len(last_minute_lines)
                conditions.append(last_minute_requests < self.rpm)

            if self.tpm is not None:
                last_minute_tokens = sum(
                    int(e.split(",")[1]) for e in last_minute_lines
                )
                conditions.append(last_minute_tokens + tokens < self.tpm)

        return all(conditions)

    def write(self, lines: list[str]):
        with open(self.file, "w") as f:
            f.writelines(lines)

    def append(self, tokens: int):
        with open(self.file, "a") as f:
            _ = f.write(f"{int(time.time())},{tokens}\n")

    def read(self) -> list[str]:
        with open(self.file, "r") as f:
            lines = f.readlines()
        return lines

    def sync(self) -> list[str]:
        cutoff = int(time.time()) - 86400  # 1 day ago
        nl = [e for e in self.read() if int(float(e.split(",")[0])) >= cutoff]
        if len(nl) < len(self.read()):
            self.write(nl)
        return nl


class Endpoint:
    def __init__(self, provider: str, model: str, properties: dict[str, str | int]):
        x = (provider + model + str(properties.get("key"))).encode()
        _hash = hashlib.sha256(x).hexdigest()
        self.eid: str = f"{provider}:{model}:{_hash[:10]}"
        self.properties: dict[str, str | int] = properties
        self.quota: QuotaManager = QuotaManager(
            id=self.eid,
            **{k: v for k, v in properties.items() if isinstance(v, int)},
        )

    def is_available(self, tokens: int) -> bool:
        return self.quota.available(tokens)

    def log(self, tokens: int):
        self.quota.append(tokens)

    def out(self) -> tuple[str, str, str, dict[str, str | int]]:
        provider, model, _ = tuple(self.eid.split(":"))
        return provider, model, self.eid, self.properties


def api_key_from_env(provider: str) -> str | None:
    return os.getenv(f"{provider.upper()}_API_KEY")


def load_endpoints_from(path: str) -> list[Endpoint]:
    configs: list[Endpoint] = []
    with open(path, "r") as f:
        header = f.readline().strip().split(",")
        for line in f:
            values = line.strip().split(",")
            row = dict(zip(header, values))
            properties: dict[str, str | int] = {}
            for quota_type in ["rpm", "tpm", "rph", "tph", "rpd", "tpd"]:
                if row[quota_type] and row[quota_type].strip():
                    properties[quota_type] = int(row[quota_type])
            key: str | None = (
                row["key"] if "key" in row else api_key_from_env(row["provider"])
            )
            if key is None:
                raise Exception(
                    f"No API key found for {row['provider']}.\
                    Set {row['provider'].upper()}_API_KEY in your env."
                )
            properties["key"] = key
            configs.append(
                Endpoint(
                    provider=row["provider"],
                    model=row["model"],
                    properties=properties,
                )
            )
    return configs


class Router:
    def __init__(self, models: list[Endpoint]):
        # ordering is implicitely given by the order of the list!
        self.endpoints: dict[str, Endpoint] = {m.eid: m for m in models}

    @staticmethod
    def from_csv(path: str) -> "Router":
        models: list[Endpoint] = load_endpoints_from(path)
        return Router(models)

    def query(
        self,
        messages: list[dict[str, str]],
        excluded: list[str] | None = None,
        autolog: bool = True,
    ) -> tuple[str, str, str, dict[str, str | int]]:
        excluded = excluded or []  # init.
        n_tokens = self.estimate_tokens(messages)
        print(n_tokens)
        for eid, endpoint in self.endpoints.items():
            if eid not in excluded and endpoint.is_available(n_tokens):
                if autolog:
                    self.log(n_tokens, eid)
                return endpoint.out()
        raise Exception("No endpoint available at this time :(")

    def log(self, tokens: int, endpoint_id: str):
        self.endpoints[endpoint_id].log(tokens)

    def estimate_tokens(self, messages: list[dict[str, str]]) -> int:
        n_chars = sum(len(m["content"]) for m in messages)
        return n_chars // 3  # very safe, fast upper bound estimate.

    def completion(
        self, messages: list[dict[str, str]], n_tries: int = 3, **kwargs
    ) -> litellm.ModelResponse:
        endpoint_ids = []
        while n_tries > 0:
            provider, model, eid, _ = self.query(
                messages, excluded=endpoint_ids, autolog=True
            )
            endpoint_ids.append(eid)
            try:
                return litellm.completion(
                    model=f"{provider}/{model}",
                    messages=messages,
                    **kwargs,
                )
            except Exception as e:
                n_tries -= 1
                if n_tries == 0:
                    raise (e)
