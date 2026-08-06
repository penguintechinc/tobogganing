"""Reverse-ordered domain trie (RadixTree) for efficient domain category lookup."""
from __future__ import annotations

import json
from typing import Any

__all__ = ["RadixTree"]


class RadixTree:
    """Reverse-ordered domain trie for O(k) subdomain-covering lookup.

    Stores domains in reverse order (com.badsite) to enable efficient
    subdomain-covering matches. A node for 'badsite.com' will match
    lookups for 'a.b.badsite.com'.
    """

    def __init__(self) -> None:
        """Initialize an empty RadixTree."""
        # Root node: maps label -> (children dict, categories tuple or None)
        self._root: dict[str, tuple[dict[str, Any], tuple[str, ...] | None]] = {}

    def insert(self, domain: str, categories: tuple[str, ...]) -> None:
        """Insert a domain and its categories into the tree.

        Args:
            domain: Domain name (e.g., 'badsite.com').
            categories: Tuple of category strings.
        """
        # Reverse the domain and split into labels
        labels = self._reverse_domain(domain)

        # Navigate/create the path
        node = self._root
        for label in labels:
            if label not in node:
                node[label] = ({}, None)
            children, _ = node[label]
            node = children

        # Mark this node as terminal with categories
        parent_label = labels[-1] if labels else ""
        if parent_label and parent_label in self._root:
            children, _ = self._root[parent_label]
            # Find the deepest node and mark it
            current = self._root
            for label in labels:
                children_dict, _ = current[label]
                current = children_dict
            # We need to store categories at this node
            # Reconstruct path
            self._set_terminal(labels, categories)
        else:
            # This is for root level or new insert
            self._set_terminal(labels, categories)

    def lookup(self, domain: str) -> tuple[str, ...] | None:
        """Look up a domain and return its categories.

        Returns the categories of the most-specific terminal node that
        covers this domain (subdomain-covering match).

        Args:
            domain: Domain name to look up.

        Returns:
            Tuple of categories, or None if not found.
        """
        labels = self._reverse_domain(domain)

        # Walk the tree and track the deepest terminal node
        node = self._root
        last_terminal_categories: tuple[str, ...] | None = None

        for label in labels:
            if label not in node:
                # Can't go deeper, return last found
                return last_terminal_categories

            children_dict, categories = node[label]
            if categories is not None:
                last_terminal_categories = categories

            node = children_dict

        return last_terminal_categories

    def serialize(self) -> bytes:
        """Serialize the tree to JSON bytes.

        Returns:
            JSON-encoded bytes representation of the tree.
        """
        # Convert tree to JSON-serializable format
        data = self._serialize_node(self._root)
        return json.dumps(data).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> RadixTree:
        """Deserialize a tree from JSON bytes.

        Args:
            data: JSON-encoded bytes from serialize().

        Returns:
            Deserialized RadixTree instance.
        """
        tree = cls()
        decoded = json.loads(data.decode("utf-8"))
        tree._root = tree._deserialize_node(decoded)
        return tree

    # Private methods

    @staticmethod
    def _reverse_domain(domain: str) -> list[str]:
        """Reverse a domain and split into labels.

        Args:
            domain: Domain name (e.g., 'badsite.com').

        Returns:
            List of labels in reverse order (e.g., ['com', 'badsite']).
        """
        labels = domain.split(".")
        labels.reverse()
        return labels

    def _set_terminal(self, labels: list[str], categories: tuple[str, ...]) -> None:
        """Set a node as terminal with categories.

        Args:
            labels: Reversed labels path.
            categories: Categories for this terminal node.
        """
        node = self._root
        for i, label in enumerate(labels):
            if label not in node:
                node[label] = ({}, None)
            children_dict, _ = node[label]
            if i == len(labels) - 1:
                # Last label: mark as terminal
                node[label] = (children_dict, categories)
            node = children_dict

    def _serialize_node(self, node: dict[str, Any]) -> dict[str, Any]:
        """Recursively serialize a node and its children.

        Args:
            node: Node dict from the tree.

        Returns:
            JSON-serializable dict.
        """
        result: dict[str, Any] = {}
        for label, (children_dict, categories) in node.items():
            result[label] = {
                "categories": list(categories) if categories else None,
                "children": self._serialize_node(children_dict),
            }
        return result

    @staticmethod
    def _deserialize_node(data: dict[str, Any]) -> dict[str, tuple[dict[str, Any], tuple[str, ...] | None]]:
        """Recursively deserialize a node and its children.

        Args:
            data: JSON-decoded dict.

        Returns:
            Node dict for the tree.
        """
        result: dict[str, tuple[dict[str, Any], tuple[str, ...] | None]] = {}
        for label, node_data in data.items():
            categories_list = node_data.get("categories")
            categories = tuple(categories_list) if categories_list else None
            children = RadixTree._deserialize_node(node_data.get("children", {}))
            result[label] = (children, categories)
        return result
