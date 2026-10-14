import docker
from docker.errors import DockerException
from fastapi import HTTPException


def get_client() -> docker.DockerClient:
    try:
        return docker.from_env()
    except DockerException as exc:
        raise HTTPException(503, f"Docker non raggiungibile: {exc}")
