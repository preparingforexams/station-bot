import base64
import json
import os
from typing import Any

import kubernetes.client
from kubernetes import client
from kubernetes.client import V1ConfigMap

from bot import Station


class State:
    def __init__(self, initial_state: dict[str, Any]):
        self.state = initial_state
        self.last_value = None

    def initialize(self):
        self.state.update(self.read(update_global_state=False))
        self.write()

    def read(self, update_global_state: bool = True) -> dict[str, Any]:
        raise NotImplementedError

    def write(self):
        raise NotImplementedError

    def set(self, key: str, value: Any):
        self.state[key] = value

    def get(self, item: str, default=None):
        return self.state.get(item, default)

    def __getitem__(self, item: str):
        return self.get(item, None)

    def __setitem__(self, key: str, value: Any):
        self.set(key, value)

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
        state["stations"] = [
            Station.deserialize(station) for station in state.get("stations", [])
        ]

        if update_global_state:
            self.state = state
        return state

    def changed(self, value):
        return self.last_value != value

    def write(self):
        state = self.state.copy()
        state["stations"]: list[dict] = [
            sstation.serialize() for sstation in state["stations"]
        ]
        value = json.dumps(state).encode("utf-8")
        value = base64.b64encode(value).decode("utf-8")
        if not self.changed(value):
            return

        if not self.configmap.data:
            self.configmap.data = {}
        self.configmap.data = {"state": value}

        self.api.patch_namespaced_config_map(self.name, self.namespace, self.configmap)
        # otherwise we're getting a 409 from the k8s api due to the version difference
        self.read(False)
        self.last_value = value
