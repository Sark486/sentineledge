from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_")

    hardware_id: str = "pi_cam_0"
    http_port: int = 8090
    lease_ttl_s: float = 5.0
    power_off_grace_s: float = 10.0
    warmup_s: float = 2.0
    jpeg_quality: int = 60
