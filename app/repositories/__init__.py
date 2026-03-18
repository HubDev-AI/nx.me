"""Repository package — data access layer.

Each repository encapsulates supabase.table/rpc/storage calls for a domain.
Handlers import repositories and call methods instead of building queries inline.
"""
