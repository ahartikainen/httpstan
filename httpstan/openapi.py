"""Define OpenAPI spec for HTTP-based REST API.

Only used for building documentation. Users should never import this file. If
they do they will likely encounter an ``ImportError`` due to the fact that they
have not installed ``apispec``.

"""

from typing import Any

from apispec import APISpec, BasePlugin
from apispec.ext.marshmallow import MarshmallowPlugin
from apispec.yaml_utils import load_operations_from_docstring

import httpstan
import httpstan.views as views

try:
    version = httpstan.__version__
except AttributeError:
    from doc.conf import version  # type: ignore


class DocPlugin(BasePlugin):
    def operation_helper(self, path: str | None, operations: dict[str, Any], **kwargs: Any) -> None:  # type: ignore
        """Operation helper that parses docstrings for operations. Adds a
        ``func`` parameter to `apispec.APISpec.path`.
        """
        view = kwargs.get("view")
        doc_operations = load_operations_from_docstring(getattr(view, "__doc__") or "")  # type: ignore
        operations.update(doc_operations)


def openapi_spec() -> APISpec:
    """Return OpenAPI (fka Swagger) spec for API."""
    spec = APISpec(
        title="httpstan HTTP-based REST API",
        version=version,
        openapi_version="3.0.3",
        # plugin order, MarshmallowPlugin resolves schema references created by DocPlugin
        plugins=[DocPlugin(), MarshmallowPlugin()],
    )
    spec.path(path="/v1/health", view=views.handle_health)
    spec.path(path="/v1/models", view=views.handle_create_model)
    spec.path(path="/v1/models", view=views.handle_list_models)
    spec.path(path="/v1/models/{model_id}", view=views.handle_delete_model)
    spec.path(path="/v1/models/{model_id}/params", view=views.handle_show_params)
    spec.path(path="/v1/models/{model_id}/log_prob", view=views.handle_log_prob)
    spec.path(path="/v1/models/{model_id}/log_prob_grad", view=views.handle_log_prob_grad)
    spec.path(path="/v1/models/{model_id}/write_array", view=views.handle_write_array)
    spec.path(path="/v1/models/{model_id}/transform_inits", view=views.handle_transform_inits)
    spec.path(path="/v1/models/{model_id}/fits", view=views.handle_create_fit)
    spec.path(path="/v1/models/{model_id}/fits/{fit_id}", view=views.handle_get_fit)
    spec.path(path="/v1/models/{model_id}/fits/{fit_id}", view=views.handle_delete_fit)
    spec.path(path="/v1/operations/{operation_id}", view=views.handle_get_operation)
    return spec
