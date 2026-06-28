import pgserver, inspect
print("pgserver attrs:", [m for m in dir(pgserver) if not m.startswith('_')])
print("get_server sig:", inspect.signature(pgserver.get_server))
print("---get_server doc---")
print(pgserver.get_server.__doc__ or "(no doc)")
print("---PostgresServer class---")
print([m for m in dir(pgserver.PostgresServer) if not m.startswith('_')])
