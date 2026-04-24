from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TemplateOutputSpec:
    output: str
    template: str

    def render_target(self, target_dir: Path) -> tuple[Path, str]:
        return (target_dir / self.output, self.template)


@dataclass(frozen=True, slots=True)
class AppTemplateSpec:
    name: str
    description: str
    outputs: tuple[TemplateOutputSpec, ...]
    port_defaults: dict[str, int]
    configurable_ports: tuple[str, ...]
    has_readme: bool
    has_healthcheck: bool
    has_dockerignore: bool

    def render_targets(self, target_dir: Path) -> list[tuple[Path, str]]:
        return [output.render_target(target_dir) for output in self.outputs]


@dataclass(frozen=True, slots=True)
class SiteTemplateSpec:
    name: str
    description: str
    outputs: tuple[TemplateOutputSpec, ...]
    has_readme: bool
    has_healthcheck: bool

    def render_targets(self, target_dir: Path) -> list[tuple[Path, str]]:
        return [output.render_target(target_dir) for output in self.outputs]


APP_TEMPLATE_SPECS: tuple[AppTemplateSpec, ...] = (
    AppTemplateSpec(
        name="placeholder",
        description="Smallest possible app scaffold.",
        outputs=(
            TemplateOutputSpec("docker-compose.yml", "app/placeholder/docker-compose.yml.j2"),
            TemplateOutputSpec(".env.example", "app/placeholder/env.example.j2"),
        ),
        port_defaults={"app": 80},
        configurable_ports=(),
        has_readme=False,
        has_healthcheck=False,
        has_dockerignore=False,
    ),
    AppTemplateSpec(
        name="static",
        description="nginx static site with starter assets.",
        outputs=(
            TemplateOutputSpec("docker-compose.yml", "app/static/docker-compose.yml.j2"),
            TemplateOutputSpec("README.md", "app/static/README.md.j2"),
            TemplateOutputSpec("html/index.html", "app/static/index.html.j2"),
            TemplateOutputSpec("html/favicon.svg", "app/static/favicon.svg.j2"),
            TemplateOutputSpec("html/assets/css/main.css", "app/static/main.css.j2"),
            TemplateOutputSpec("html/assets/js/main.js", "app/static/main.js.j2"),
            TemplateOutputSpec("html/assets/images/.gitkeep", "app/static/images.gitkeep.j2"),
        ),
        port_defaults={"site": 80},
        configurable_ports=(),
        has_readme=True,
        has_healthcheck=True,
        has_dockerignore=False,
    ),
    AppTemplateSpec(
        name="static-api",
        description="Static site plus a small Python API.",
        outputs=(
            TemplateOutputSpec("docker-compose.yml", "app/static-api/docker-compose.yml.j2"),
            TemplateOutputSpec(".dockerignore", "app/static-api/dockerignore.j2"),
            TemplateOutputSpec("README.md", "app/static-api/README.md.j2"),
            TemplateOutputSpec("html/index.html", "app/static-api/index.html.j2"),
            TemplateOutputSpec("html/favicon.svg", "app/static-api/favicon.svg.j2"),
            TemplateOutputSpec("html/assets/css/main.css", "app/static-api/main.css.j2"),
            TemplateOutputSpec("html/assets/js/main.js", "app/static-api/main.js.j2"),
            TemplateOutputSpec("html/assets/images/.gitkeep", "app/static-api/images.gitkeep.j2"),
            TemplateOutputSpec("api/Dockerfile", "app/static-api/api.Dockerfile.j2"),
            TemplateOutputSpec("api/requirements.txt", "app/static-api/api.requirements.txt.j2"),
            TemplateOutputSpec("api/app/main.py", "app/static-api/api.main.py.j2"),
        ),
        port_defaults={"site": 80, "api": 8000},
        configurable_ports=("api",),
        has_readme=True,
        has_healthcheck=True,
        has_dockerignore=True,
    ),
    AppTemplateSpec(
        name="node",
        description="Node app scaffold with healthcheck.",
        outputs=(
            TemplateOutputSpec("docker-compose.yml", "app/node/docker-compose.yml.j2"),
            TemplateOutputSpec(".env.example", "app/node/env.example.j2"),
            TemplateOutputSpec(".dockerignore", "app/node/dockerignore.j2"),
            TemplateOutputSpec("Dockerfile", "app/node/Dockerfile.j2"),
            TemplateOutputSpec("README.md", "app/node/README.md.j2"),
            TemplateOutputSpec("package.json", "app/node/package.json.j2"),
            TemplateOutputSpec("src/server.js", "app/node/src/server.js.j2"),
        ),
        port_defaults={"app": 3000},
        configurable_ports=("app",),
        has_readme=True,
        has_healthcheck=True,
        has_dockerignore=True,
    ),
    AppTemplateSpec(
        name="python",
        description="Python app scaffold with healthcheck.",
        outputs=(
            TemplateOutputSpec("docker-compose.yml", "app/python/docker-compose.yml.j2"),
            TemplateOutputSpec(".env.example", "app/python/env.example.j2"),
            TemplateOutputSpec(".dockerignore", "app/python/dockerignore.j2"),
            TemplateOutputSpec("Dockerfile", "app/python/Dockerfile.j2"),
            TemplateOutputSpec("README.md", "app/python/README.md.j2"),
            TemplateOutputSpec("requirements.txt", "app/python/requirements.txt.j2"),
            TemplateOutputSpec("app/main.py", "app/python/app/main.py.j2"),
        ),
        port_defaults={"app": 8000},
        configurable_ports=("app",),
        has_readme=True,
        has_healthcheck=True,
        has_dockerignore=True,
    ),
    AppTemplateSpec(
        name="jekyll",
        description="Jekyll build plus static serving baseline.",
        outputs=(
            TemplateOutputSpec("docker-compose.yml", "app/jekyll/docker-compose.yml.j2"),
            TemplateOutputSpec(".dockerignore", "app/jekyll/dockerignore.j2"),
            TemplateOutputSpec("Dockerfile", "app/jekyll/Dockerfile.j2"),
            TemplateOutputSpec("README.md", "app/jekyll/README.md.j2"),
            TemplateOutputSpec("site/Gemfile", "app/jekyll/site.Gemfile.j2"),
            TemplateOutputSpec("site/_config.yml", "app/jekyll/site._config.yml.j2"),
            TemplateOutputSpec("site/index.md", "app/jekyll/site.index.md.j2"),
        ),
        port_defaults={"site": 80},
        configurable_ports=(),
        has_readme=True,
        has_healthcheck=True,
        has_dockerignore=True,
    ),
    AppTemplateSpec(
        name="rust-react-postgres",
        description="Rust API plus React/Vite frontend and internal Postgres.",
        outputs=(
            TemplateOutputSpec("docker-compose.yml", "app/rust-react-postgres/docker-compose.yml.j2"),
            TemplateOutputSpec(".env.example", "app/rust-react-postgres/env.example.j2"),
            TemplateOutputSpec(".dockerignore", "app/rust-react-postgres/dockerignore.j2"),
            TemplateOutputSpec("README.md", "app/rust-react-postgres/README.md.j2"),
            TemplateOutputSpec("frontend/Dockerfile", "app/rust-react-postgres/frontend.Dockerfile.j2"),
            TemplateOutputSpec("frontend/nginx.conf", "app/rust-react-postgres/frontend.nginx.conf.j2"),
            TemplateOutputSpec("frontend/package.json", "app/rust-react-postgres/frontend.package.json.j2"),
            TemplateOutputSpec("frontend/vite.config.js", "app/rust-react-postgres/frontend.vite.config.js.j2"),
            TemplateOutputSpec("frontend/index.html", "app/rust-react-postgres/frontend.index.html.j2"),
            TemplateOutputSpec("frontend/src/main.jsx", "app/rust-react-postgres/frontend.src.main.jsx.j2"),
            TemplateOutputSpec("frontend/src/App.jsx", "app/rust-react-postgres/frontend.src.App.jsx.j2"),
            TemplateOutputSpec("frontend/src/styles.css", "app/rust-react-postgres/frontend.src.styles.css.j2"),
            TemplateOutputSpec("api/Dockerfile", "app/rust-react-postgres/api.Dockerfile.j2"),
            TemplateOutputSpec("api/Cargo.toml", "app/rust-react-postgres/api.Cargo.toml.j2"),
            TemplateOutputSpec("api/src/main.rs", "app/rust-react-postgres/api.src.main.rs.j2"),
            TemplateOutputSpec("api/migrations/0001_initial.sql", "app/rust-react-postgres/api.migrations.0001_initial.sql.j2"),
        ),
        port_defaults={"frontend": 80, "api": 8080, "postgres": 5432},
        configurable_ports=("api",),
        has_readme=True,
        has_healthcheck=True,
        has_dockerignore=True,
    ),
)

SITE_TEMPLATE_SPEC = SiteTemplateSpec(
    name="static",
    description="Minimal two-file site scaffold for site init.",
    outputs=(
        TemplateOutputSpec("docker-compose.yml", "static/docker-compose.yml.j2"),
        TemplateOutputSpec("html/index.html", "static/index.html.j2"),
    ),
    has_readme=False,
    has_healthcheck=False,
)


def app_template_names() -> list[str]:
    return [template.name for template in APP_TEMPLATE_SPECS]


def app_template_options() -> list[tuple[str, str]]:
    return [(template.name, template.description) for template in APP_TEMPLATE_SPECS]


def app_template_spec(name: str) -> AppTemplateSpec:
    for template in APP_TEMPLATE_SPECS:
        if template.name == name:
            return template
    available = ", ".join(app_template_names())
    raise ValueError(f"unknown app template `{name}`. Expected one of: {available}")


def expected_packaged_template_files() -> set[str]:
    expected = {spec.template for spec in SITE_TEMPLATE_SPEC.outputs}
    for template in APP_TEMPLATE_SPECS:
        expected.update(spec.template for spec in template.outputs)
    return {f"homesrvctl/templates/{template_path}" for template_path in expected}
