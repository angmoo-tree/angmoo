"""Content-free, consistent fingerprint of every PG table and sequence."""
import argparse,hashlib,json,re
from pathlib import Path
import psycopg
from psycopg import sql
from app.runtime.postgresql_backend import install_validation_guards


def normalize_definition(value):
    # pg_dump/reparse moves an explicit varchar[] -> text[] coercion onto
    # each varchar constant. Only this exact constant-array form is equivalent.
    literal=r"'(?:[^']|'')*'"
    element=literal+r'::character varying'
    pattern=r'\(\(ARRAY\[('+element+r'(?:, '+element+r')*)\]\)::text\[\]\)'
    value=re.sub(pattern,lambda m:'(ARRAY['+m[1].replace('::character varying','::text')+'])',value)
    return re.sub(r'\(('+literal+r')::character varying\)::text',r'\1::text',value)


def comparable(value):
    value=dict(value)
    for category in ('constraints','indexes','triggers'):
        value[category]=[[*row[:-1],normalize_definition(row[-1])] for row in value.get(category,[])]
    return value


def fingerprint(dsn):
    with psycopg.connect(dsn.replace('postgresql+psycopg://','postgresql://',1)) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        tables=conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
        rows={}
        for (table,) in tables:
            h=hashlib.sha256();count=0
            with conn.cursor(name='fingerprint') as cursor:
                cursor.execute(sql.SQL('SELECT md5(row_to_json(t)::text) FROM {} t ORDER BY 1').format(sql.Identifier(table)))
                for (digest,) in cursor:h.update(digest.encode());count+=1
            rows[table]={'count':count,'digest':h.hexdigest()}
        sequences=conn.execute("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename").fetchall()
        extensions=conn.execute('SELECT extname,extversion FROM pg_extension ORDER BY extname').fetchall()
        constraints=conn.execute("SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY 1,2").fetchall()
        indexes=conn.execute("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1,2").fetchall()
        triggers=conn.execute("SELECT tgrelid::regclass::text,tgname,pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN(SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace) ORDER BY 1,2").fetchall()
        permissions=conn.execute("SELECT relname,relacl::text,pg_get_userbyid(relowner) FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN('r','S') ORDER BY 1").fetchall()
        return {'tables':rows,'sequences':sequences,'extensions':extensions,'constraints':constraints,'indexes':indexes,'triggers':triggers,'permissions':permissions}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dsn-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    install_validation_guards()
    result=fingerprint(a.dsn_file.read_text().strip())
    with a.output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps({'state':'FINGERPRINTED','tables':len(result['tables'])}))
