"""Actual-device gate for synthetic PG data, including crash recovery."""
import concurrent.futures,datetime,json,os,pathlib,subprocess,time
from phone_pg import ROOT,ROLE,PORT,command,environment,identity,root,run,sql,start,stop,record,verify_postmaster
from guard import RUN_ID,SOURCE_SHA
DB='angmoo_pg_run01_g1'

def checked(statement,db=DB):
    result=sql(statement,db=db,timeout=45)
    if result['returncode']:raise RuntimeError(json.dumps(result))
    return result['stdout'].strip()

def snapshot():
    base=root();binary=str(base/'tools/proot-playstore');pg=str(base/'rootfs/usr/lib/postgresql/17/bin/postgres')
    rows={};errors=[]
    for p in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            if p.stat().st_uid!=os.getuid():continue
            maps=(p/'maps').read_text()
            if binary not in maps and pg not in maps:continue
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            if fields[0]=='Z':continue
            rollup=(p/'smaps_rollup').read_text().splitlines()
            pss=int(next(l for l in rollup if l.startswith('Pss:')).split()[1])
            rows[p.name+':'+fields[19]]={'pid':int(p.name),'pss_kib':pss,'cpu_ticks':int(fields[11])+int(fields[12])}
        except (PermissionError,FileNotFoundError,ProcessLookupError):continue
        except (ValueError,StopIteration) as ex:errors.append(type(ex).__name__)
    mem={l.split(':')[0]:l.split(':')[1].strip() for l in pathlib.Path('/proc/meminfo').read_text().splitlines()}
    return {'monotonic':time.monotonic(),'processes':rows,'pss_kib':sum(x['pss_kib'] for x in rows.values()),
            'mem_available_kib':int(mem['MemAvailable'].split()[0]),'errors':errors}

def sample(seconds):
    samples=[snapshot()]
    for _ in range(seconds):time.sleep(1);samples.append(snapshot())
    cpu=0;departed=[]
    for a,b in zip(samples,samples[1:]):
        for pid,v in b['processes'].items():
            old=a['processes'].get(pid)
            if old:cpu+=max(0,v['cpu_ticks']-old['cpu_ticks'])
        departed.extend(k for k in a['processes'] if k not in b['processes'])
    elapsed=samples[-1]['monotonic']-samples[0]['monotonic'];cpu_s=cpu/os.sysconf('SC_CLK_TCK')
    return {'seconds':elapsed,'peak_pss_mib':max(s['pss_kib'] for s in samples)/1024,
        'min_mem_available_mib':min(s['mem_available_kib'] for s in samples)/1024,
        'cpu_seconds_observed':cpu_s,'cpu_one_core_percent':100*cpu_s/elapsed,
        'cpu_all_cores_percent':100*cpu_s/elapsed/os.cpu_count(),'departed_between_samples':sorted(set(departed)),
        'cpu_note':'Only owned PG and PRoot mappings; short-lived exits between samples can undercount and are reported.',
        'samples':samples}

def client(statement):
    return subprocess.Popen(command('psql','-X','-w','-h','127.0.0.1','-p',str(PORT),'-U',ROLE,'-d',DB,
        '-v','ON_ERROR_STOP=1','-At','-c',statement),env=environment(),stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)

def main():
    root();result={'run_id':RUN_ID,'kind':'G1 actual Android ARM64 image/PRoot, synthetic data only','checks':{}}
    exists=checked("SELECT count(*) FROM pg_database WHERE datname='"+DB+"';",db='postgres')=='1'
    if exists:
        assert checked('SELECT run_id FROM angmoo_experiment_identity;')==RUN_ID
        assert checked('SELECT source_sha FROM angmoo_experiment_identity;')==SOURCE_SHA
        assert checked('SELECT count(*) FROM g1_memory;')=='3'
        result['resumed_owned_synthetic_database']=True
    else:
        checked('CREATE DATABASE '+DB+';',db='postgres')
        checked(f"CREATE TABLE angmoo_experiment_identity(singleton boolean PRIMARY KEY CHECK(singleton),run_id text NOT NULL,source_sha text NOT NULL); INSERT INTO angmoo_experiment_identity VALUES(TRUE,'{RUN_ID}','{SOURCE_SHA}');")
        checked('CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;')
    result['checks']['extension']=checked("SELECT extname||':'||extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm') ORDER BY extname;")
    if not exists:checked("""CREATE TABLE g1_memory(id int PRIMARY KEY,scope text NOT NULL,body text NOT NULL,embedding vector(768) NOT NULL,
        keywords tsvector GENERATED ALWAYS AS (to_tsvector('simple',body)) STORED);
        CREATE INDEX g1_keywords ON g1_memory USING gin(keywords);
        INSERT INTO g1_memory VALUES(1,'a','메이 화원 산책', (ARRAY[1::real]||array_fill(0::real,ARRAY[767]))::vector),
        (2,'a','태오 도서관', (ARRAY[0::real,1::real]||array_fill(0::real,ARRAY[766]))::vector),
        (3,'other','메이 비공개', (ARRAY[1::real]||array_fill(0::real,ARRAY[767]))::vector);
        CREATE TABLE g1_counters(id int PRIMARY KEY,value int NOT NULL); INSERT INTO g1_counters VALUES(1,0),(2,0);
        CREATE TABLE g1_receipts(id text PRIMARY KEY,committed boolean NOT NULL);""")
    nearest=checked("SELECT id FROM g1_memory WHERE scope='a' ORDER BY embedding <=> (ARRAY[1::real]||array_fill(0::real,ARRAY[767]))::vector,id LIMIT 1;")
    assert nearest=='1';result['checks']['exact_768_cosine_scope']='pass'
    assert checked("SELECT id FROM g1_memory WHERE scope='a' AND keywords @@ plainto_tsquery('simple','메이');")=='1'
    result['checks']['fts_korean_smoke']='pass; full Korean parity belongs to G3'
    checked("BEGIN; INSERT INTO g1_receipts VALUES('rolled_back',true); ROLLBACK;")
    assert checked("SELECT count(*) FROM g1_receipts WHERE id='rolled_back';")=='0'
    checked("INSERT INTO g1_receipts VALUES('committed',true) ON CONFLICT(id) DO NOTHING;")
    result['checks']['transaction_commit_rollback']='pass'
    overlaps={}
    for label,ids in [('different_rows',[1,2]),('same_row',[1,1])]:
        checked('UPDATE g1_counters SET value=0;')
        def write(i):
            return checked(f"BEGIN; UPDATE g1_counters SET value=value+1 WHERE id={i}; SELECT clock_timestamp(); SELECT pg_sleep(0.8); SELECT clock_timestamp(); COMMIT;")
        start_time=time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:outputs=list(pool.map(write,ids))
        intervals=[]
        for output in outputs:
            stamps=[datetime.datetime.fromisoformat(l) for l in output.splitlines() if l[:4].isdigit() and '+' in l]
            assert len(stamps)==2;intervals.append(stamps)
        overlap=max(0,(min(x[1] for x in intervals)-max(x[0] for x in intervals)).total_seconds())
        values=checked('SELECT id,value FROM g1_counters ORDER BY id;')
        assert values==('1|1\n2|1' if label=='different_rows' else '1|2\n2|0')
        if label=='different_rows':assert overlap>0.3
        else:assert overlap<0.05
        overlaps[label]={'elapsed_seconds':time.monotonic()-start_time,'overlap_seconds':overlap,'values':values}
    result['checks']['concurrent_writes']=overlaps
    result['idle']=sample(30)
    load=client("DO $$ DECLARE until_at timestamptz := clock_timestamp()+interval '32 seconds'; BEGIN WHILE clock_timestamp()<until_at LOOP PERFORM sum(i) FROM generate_series(1,10000) i; END LOOP; END $$; SELECT pg_sleep(3);")
    time.sleep(.5);result['short_load']=sample(30)
    out,err=load.communicate(timeout=15)
    assert load.returncode==0,err
    result['checks']['short_load']='pass'
    record('g1-progress.json',result)
    result['clean_stop']=stop();assert result['clean_stop']['returncode']==0
    result['clean_restart']=start();assert result['clean_restart']['status']=='ready'
    assert checked("SELECT count(*) FROM g1_receipts WHERE id='committed';")=='1'
    result['checks']['clean_restart_persistence']='pass'
    record('g1-progress.json',result)
    uncommitted=client("SET application_name='angmoo_g1_uncommitted'; BEGIN; UPDATE g1_counters SET value=9999 WHERE id=1; SELECT pg_sleep(30); COMMIT;")
    for _ in range(30):
        if checked("SELECT count(*) FROM pg_stat_activity WHERE application_name='angmoo_g1_uncommitted' AND wait_event='PgSleep';")=='1':break
        time.sleep(.1)
    else:raise RuntimeError('uncommitted_transaction_not_observed')
    result['crash']=stop(crash=True)
    uncommitted.communicate(timeout=10)
    result['crash_restart']=start();assert result['crash_restart']['status']=='ready',result['crash_restart']
    assert checked('SELECT value FROM g1_counters WHERE id=1;')=='2'
    assert checked("SELECT count(*) FROM g1_receipts WHERE id='committed';")=='1'
    assert checked("SELECT count(*) FROM g1_memory WHERE keywords @@ plainto_tsquery('simple','메이');")=='2'
    result['checks']['crash_committed_kept_uncommitted_rolled_back']='pass'
    result['final_stop']=stop();assert result['final_stop']['returncode']==0
    result['checksums']=run('pg_checksums','--check','-D','/var/lib/postgresql/data',timeout=60)
    assert result['checksums']['returncode']==0,result['checksums']
    result['status']='pass_with_experiment_local_proot_compatibility_patch'
    result['not_proven']=['Angmoo functional port','migration','three-service total resources','G5 long-running/screen-off/battery','real AI']
    record('g1-results.json',result)
    return result

if __name__=='__main__':print(json.dumps(main(),ensure_ascii=False,indent=2))
