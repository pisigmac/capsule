"""Unit and integration tests for OCI Container Registry Distribution."""
from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest
import respx
import httpx
from click.testing import CliRunner

from capsule_cli.main import cli
from services.registry.oci.auth import OCIAuthManager
from services.registry.oci.client import OCIClient, OCIClientError
from services.registry.oci.manifest import build_oci_manifest, CapsuleOCIConfig
from services.registry.oci.packager import OCIPackager, TarSlipError
from services.registry.oci.reference import (
    OCIReference,
    is_oci_reference,
    parse_oci_reference,
)
from services.shared.models import Capsule


class TestOCIReference:
    def test_parse_full_ghcr_reference(self):
        ref = parse_oci_reference("ghcr.io/pisigmac/capsule-memory:v1.0.0")
        assert ref.registry == "ghcr.io"
        assert ref.repository == "pisigmac/capsule-memory"
        assert ref.tag == "v1.0.0"
        assert ref.digest is None
        assert ref.identifier == "v1.0.0"
        assert not ref.is_digest

    def test_parse_digest_reference(self):
        ref = parse_oci_reference("ghcr.io/org/repo@sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        assert ref.registry == "ghcr.io"
        assert ref.repository == "org/repo"
        assert ref.digest == "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert ref.is_digest
        assert ref.identifier == "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_parse_docker_hub_shorthand(self):
        ref = parse_oci_reference("docker.io/myuser/mypack:2.0")
        assert ref.registry == "registry-1.docker.io"
        assert ref.repository == "myuser/mypack"
        assert ref.tag == "2.0"

    def test_parse_localhost_reference(self):
        ref = parse_oci_reference("localhost:5000/local-caps:dev")
        assert ref.registry == "localhost:5000"
        assert ref.repository == "local-caps"
        assert ref.tag == "dev"

    def test_is_oci_reference_detection(self):
        assert is_oci_reference("ghcr.io/org/repo:1.0") is True
        assert is_oci_reference("org/repo:1.0") is True
        assert is_oci_reference("localhost:5000/pack") is True
        assert is_oci_reference("python-best-practices") is False
        assert is_oci_reference("fastapi-security") is False


class TestOCIPackager:
    def test_pack_and_unpack_layer(self, tmp_path):
        source = tmp_path / "source_caps"
        source.mkdir()

        (source / "rule1.caps.md").write_text(
            "---\ntopic: OCI Rule 1\ntags: [oci, docker]\nconfidence: high\n---\n\nRule 1 content",
            encoding="utf-8",
        )
        (source / "rule2.caps.md").write_text(
            "---\ntopic: OCI Rule 2\ntags: [registry]\nconfidence: high\n---\n\nRule 2 content",
            encoding="utf-8",
        )

        layer_bytes, digest, size = OCIPackager.pack_layer(source)
        assert layer_bytes is not None
        assert digest.startswith("sha256:")
        assert size == len(layer_bytes)

        target = tmp_path / "extracted_caps"
        installed, skipped = OCIPackager.unpack_layer(layer_bytes, target)
        assert len(installed) == 2
        assert "rule1.caps.md" in installed
        assert "rule2.caps.md" in installed
        assert (target / "rule1.caps.md").exists()

    def test_tar_slip_defense(self, tmp_path):
        # Craft a malicious tar.gz containing ../evil.caps.md
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo(name="../../../evil.caps.md")
            content = b"malicious content"
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))

        malicious_bytes = buf.getvalue()
        target = tmp_path / "safe_extract"

        with pytest.raises(TarSlipError):
            OCIPackager.unpack_layer(malicious_bytes, target)


class TestOCIAuthManager:
    def test_store_and_retrieve_credentials(self, tmp_path):
        config_path = tmp_path / "docker_config.json"
        auth_mgr = OCIAuthManager(config_path=config_path)

        auth_mgr.store_credentials("ghcr.io", "testuser", "testsecret")
        assert config_path.is_file()

        creds = auth_mgr.get_credentials("ghcr.io")
        assert creds == ("testuser", "testsecret")


class TestOCIClientOperations:
    @respx.mock
    def test_push_and_pull_workflow(self, tmp_path, db_session):
        # Setup source capsules
        source = tmp_path / "source_caps"
        source.mkdir()
        (source / "sec.caps.md").write_text(
            "---\ntopic: JWT Secret Rotation\ntags: [security, jwt]\nconfidence: high\n---\n\nRotate secrets quarterly.",
            encoding="utf-8",
        )

        # Build local layer to get exact digests for mocking
        layer_bytes, layer_digest, layer_size = OCIPackager.pack_layer(source)
        cfg = CapsuleOCIConfig(author="Tester", description="Test OCI", caps_count=1, tags=["security"])
        cfg_bytes, cfg_digest, cfg_size = cfg.to_bytes()
        manifest_dict, manifest_bytes, manifest_digest, manifest_size = build_oci_manifest(
            config_digest=cfg_digest,
            config_size=cfg_size,
            layer_digest=layer_digest,
            layer_size=layer_size,
        )

        # Mock OCI registry endpoints on mockregistry.io
        import re
        base = "https://mockregistry.io/v2/testorg/testpack"

        # Push endpoints
        respx.head(re.compile(f"^{base}/blobs/sha256:.*")).mock(return_value=httpx.Response(404))
        respx.post(f"{base}/blobs/uploads/").mock(
            return_value=httpx.Response(202, headers={"Location": f"/v2/testorg/testpack/blobs/uploads/upload-chunk"})
        )
        respx.put(re.compile(f"^{base}/blobs/uploads/upload-chunk.*")).mock(return_value=httpx.Response(201))
        respx.put(f"{base}/manifests/1.0.0").mock(return_value=httpx.Response(201))

        # Pull endpoints
        respx.get(f"{base}/manifests/1.0.0").mock(
            return_value=httpx.Response(200, content=manifest_bytes, headers={"Content-Type": "application/vnd.oci.image.manifest.v1+json"})
        )
        respx.get(f"{base}/blobs/{layer_digest}").mock(
            return_value=httpx.Response(200, content=layer_bytes)
        )
        respx.get(f"{base}/blobs/{cfg_digest}").mock(
            return_value=httpx.Response(200, content=cfg_bytes)
        )

        client = OCIClient()

        # 1. Test Push
        push_res = client.push(source, reference="mockregistry.io/testorg/testpack:1.0.0", author="Tester")
        assert push_res.layer_digest == layer_digest
        assert push_res.caps_count == 1
        assert push_res.manifest_digest.startswith("sha256:")

        # 2. Test Inspect
        inspect_res = client.inspect("mockregistry.io/testorg/testpack:1.0.0")
        assert inspect_res["reference"] == "mockregistry.io/testorg/testpack:1.0.0"
        assert len(inspect_res["layers"]) == 1

        # 3. Test Pull
        target = tmp_path / "extracted_target"
        pull_res = client.pull("mockregistry.io/testorg/testpack:1.0.0", target_dir=target, db_session=db_session)
        assert pull_res.total_installed == 1
        assert (target / "sec.caps.md").exists()
        assert pull_res.reconciled is True
        assert db_session.query(Capsule).count() == 1


class TestOCICliCommands:
    def test_push_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["push", "--help"])
        assert result.exit_code == 0
        assert "Push a directory of capsules to an OCI container registry" in result.output

    def test_login_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["login", "--help"])
        assert result.exit_code == 0
        assert "Authenticate with an OCI container registry" in result.output

    def test_inspect_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "Inspect remote OCI artifact manifest" in result.output

    def test_login_cli_execution(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "custom_docker_config.json"
        monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["login", "ghcr.io", "-u", "testuser", "-p", "ghp_secret123"])
        assert result.exit_code == 0
        assert "Login Succeeded" in result.output
        assert (tmp_path / "config.json").is_file()
