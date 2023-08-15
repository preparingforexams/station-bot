import base64
import json
import os
from typing import Any, Optional

import kubernetes.client
from kubernetes import client
from kubernetes.client import V1ConfigMap

from . import Station


class State:
    def __init__(self, initial_state: dict[str, Any]):
        self.state = initial_state
        self.bot = None
        self.changed = True

    def initialize(self):
        self.state.update(self.read())
        self.write()

    def read(self) -> dict[str, Any]:
        raise NotImplemented

    def write(self):
        raise NotImplemented

    def set(self, key: str, value: Any):
        self.changed = True
        self.state[key] = value

    def get(self, item: str, default=None):
        return self.state.get(item, default)

    def __getitem__(self, item: str):
        return self.get(item, None)

    def __setitem__(self, key: str, value: Any):
        self.set(key, value)


class ConfigmapState(State):
    def __init__(self, kubernetes_api_client, state: dict[str, Any]):
        self.api: kubernetes.client.CoreV1Api = kubernetes_api_client
        self.name = os.getenv("CONFIGMAP_NAME")
        self.namespace = os.getenv("CONFIGMAP_NAMESPACE")

        if not self.name or not self.namespace:
            raise ValueError("`CONFIGMAP_NAME` and `CONFIGMAP_NAMESPACE` have to be defined")
        self.configmap: Optional[V1ConfigMap] = None
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
                data={}
            )
            self.api.create_namespaced_config_map(self.namespace, configmap)

        super().initialize()

    def read(self) -> dict[str, Any]:
        self.configmap = self.api.read_namespaced_config_map(self.name, self.namespace)
        if self.configmap.data is None and not self.state:
            state = {}
        else:
            state = json.loads(base64.b64decode(self.configmap.data["state"]).decode("utf-8"))
            state["stations"] = [Station.serialize(station) for station in state.get("stations", [])]

        return state

    def write(self):
        if not self.changed:
            return

        state = self.state.copy()
        state["stations"]: list[Station] = [station.deserialize() for station in state["stations"]]
        value = json.dumps(state).encode("utf-8")
        value = base64.b64encode(value).decode("utf-8")
        if not self.configmap.data:
            self.configmap.data = {}
        self.configmap.data["state"] = value

        self.api.patch_namespaced_config_map(self.name, self.namespace, self.configmap)
        # otherwise we're getting a 409 from the k8s api due to the version difference
        self.read()
        self.changed = False
