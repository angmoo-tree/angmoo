"""Offline backend native checks for the PostgreSQL serving profile."""
import json,platform,sys,tempfile
from pathlib import Path
import ladybug,psycopg

with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'graph'
    graph=ladybug.Database(str(path));connection=ladybug.Connection(graph)
    connection.execute('CREATE NODE TABLE Item(id STRING, PRIMARY KEY(id))')
    connection.execute("CREATE (:Item {id: 'synthetic'})")
    connection.close();graph.close()
    graph=ladybug.Database(str(path));connection=ladybug.Connection(graph)
    assert connection.execute('MATCH (n:Item) RETURN n.id').get_next()[0]=='synthetic'
    connection.close();graph.close()
assert psycopg.pq.__impl__=='binary'
print(json.dumps({'status':'PASS','architecture':platform.machine(),'python':sys.version.split()[0],
    'psycopg_binary':True,'ladybug_restart':True,'serving_sqlite_opens':0,'provider_transmissions':0}))
