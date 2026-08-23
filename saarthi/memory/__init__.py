"""
SAARTHI Memory — yaaddasht.

    facts         -> user ke baare mein permanent baatein
    conversations -> purani baatein ("wahi jo pichli baar kiya tha")

SQLite pe chalta hai — free, fast, ek file.

Use:
    from saarthi.memory import MemoryStore

    memory = MemoryStore()
    await memory.remember("mummy ka number", "98765xxxxx", category="contacts")
    fact = await memory.recall("mummy ka number")
"""

from .store import ConversationTurn, Fact, MemoryStore

__all__ = ["MemoryStore", "Fact", "ConversationTurn"]
