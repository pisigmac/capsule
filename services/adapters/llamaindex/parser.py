"""LlamaIndex Node Parser adapter for Capsule markdown documents."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from pydantic import Field

try:
    from llama_index.core.node_parser.interface import NodeParser
    from llama_index.core.schema import (
        BaseNode,
        Document,
        NodeRelationship,
        RelatedNodeInfo,
        TextNode,
    )
except ImportError as exc:
    raise ImportError(
        "The LlamaIndex adapter requires 'llama-index-core'. "
        "Please install it with: pip install kapsule[llamaindex] or pip install llama-index-core"
    ) from exc

from services.parser.parser import CapsuleParser


class CapsuleNodeParser(NodeParser):
    """Custom LlamaIndex NodeParser that transforms Markdown/Capsule documents into atomic TextNodes."""

    include_metadata: bool = Field(default=True, description="Whether to preserve and extract metadata")
    include_prev_next_rel: bool = Field(default=True, description="Whether to include previous/next node relationships")

    @classmethod
    def class_name(cls) -> str:
        return "CapsuleNodeParser"

    def _parse_nodes(
        self,
        documents: Sequence[Document],
        show_progress: bool = False,
        **kwargs: Any,
    ) -> List[BaseNode]:
        """Parse raw documents into atomic Capsule TextNodes."""
        parser = CapsuleParser()
        nodes: List[BaseNode] = []

        for doc in documents:
            parsed = parser.parse_text(doc.text, file_path=doc.metadata.get("file_path"))

            metadata: Dict[str, Any] = {}
            if self.include_metadata:
                # Merge document metadata first
                metadata.update(doc.metadata)

                # Overlay parsed metadata
                if parsed.topic:
                    metadata["topic"] = parsed.topic
                if parsed.tags:
                    metadata["tags"] = parsed.tags
                if parsed.confidence:
                    metadata["confidence"] = parsed.confidence
                if parsed.source:
                    metadata["source"] = parsed.source
                if parsed.archived is not None:
                    metadata["archived"] = parsed.archived
                if parsed.id:
                    metadata["id"] = parsed.id
                if parsed.freshness:
                    metadata["freshness"] = (
                        parsed.freshness.isoformat()
                        if hasattr(parsed.freshness, "isoformat")
                        else str(parsed.freshness)
                    )

            # Filter out None values
            metadata = {k: v for k, v in metadata.items() if v is not None}

            text = f"{parsed.topic}\n\n{parsed.content}".strip() if parsed.topic else parsed.content
            node_id = parsed.id or doc.id_

            node = TextNode(
                id_=node_id,
                text=text,
                metadata=metadata,
                relationships={
                    NodeRelationship.SOURCE: RelatedNodeInfo(
                        node_id=doc.id_,
                        metadata={"file_path": doc.metadata.get("file_path")},
                    )
                },
            )
            nodes.append(node)

        if self.include_prev_next_rel and len(nodes) > 1:
            for i in range(len(nodes)):
                if i > 0:
                    nodes[i].relationships[NodeRelationship.PREVIOUS] = RelatedNodeInfo(
                        node_id=nodes[i - 1].node_id
                    )
                if i < len(nodes) - 1:
                    nodes[i].relationships[NodeRelationship.NEXT] = RelatedNodeInfo(
                        node_id=nodes[i + 1].node_id
                    )

        return nodes
