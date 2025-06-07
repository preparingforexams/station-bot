import asyncio
import base64
import json
import os
from typing import Any

import kubernetes.client
from kubernetes import client, config
from kubernetes.client import V1ConfigMap


class State:
    def __init__(self, initial_state: dict[str, Any]):
        self.state = initial_state
        self.last_value = None

    def initialize(self):
        self.state.update(self.read(update_global_state=False))

    def read(self, update_global_state: bool = True) -> dict[str, Any]:
        raise NotImplementedError

    def get(self, item: str, default=None):
        return self.state.get(item, default)

    def __getitem__(self, item: str):
        return self.get(item, None)

    def items(self):
        return self.state.items()


class ConfigmapState(State):
    def __init__(self, kubernetes_api_client, state: dict[str, Any]):
        self.api: kubernetes.client.CoreV1Api = kubernetes_api_client
        self.name = os.getenv("CONFIGMAP_NAME")
        self.namespace = os.getenv("CONFIGMAP_NAMESPACE")

        if not self.name or not self.namespace:
            raise ValueError(
                "`CONFIGMAP_NAME` and `CONFIGMAP_NAMESPACE` have to be defined"
            )
        self.configmap: V1ConfigMap | None = None
        super().__init__(state)

    def initialize(self):
        create = True

        for configmap in self.api.list_namespaced_config_map(self.namespace).items:
            if configmap.metadata.name == self.name:
                create = False
                break

        if create:
            configmap = client.V1ConfigMap(
                api_version="v1",
                kind="ConfigMap",
                metadata=client.V1ObjectMeta(
                    name=self.name,
                    namespace=self.namespace,
                ),
                data={},
            )
            self.configmap = self.api.create_namespaced_config_map(
                self.namespace, configmap
            )
            self.configmap.data = self.state

        super().initialize()

    def read(self, update_global_state: bool = True) -> dict[str, Any]:
        self.configmap = self.api.read_namespaced_config_map(self.name, self.namespace)

        if not self.configmap.data:
            self.configmap.data = {"state": base64.b64encode(b'{"stations": []}')}

        decoded_value = base64.b64decode(self.configmap.data["state"]).decode("utf-8")
        state = json.loads(decoded_value)
        state["stations"] = [station for station in state.get("stations", [])]

        if update_global_state:
            self.state = state
        return state


def __read_legacy_state() -> dict[str, Any]:
    try:
        config.load_incluster_config()
    except config.config_exception.ConfigException:
        config.load_kube_config()

    with client.ApiClient() as api_client:
        api = client.CoreV1Api(api_client)
        state = ConfigmapState(api, {})
        state.initialize()
        return state.read(update_global_state=False)


async def read_legacy_state() -> dict[str, Any]:
    return await asyncio.get_running_loop().run_in_executor(None, __read_legacy_state)
