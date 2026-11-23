"""Run the declared synthetic Stage 2 ADS study in fresh evidence directories.

Execute in ADS Python through MCP or the documented ADS automation environment.
The native schematic is the simulation input. Independent calculations predict
and check data; they never substitute for simulator outputs.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time

import numpy as np

try:
    from . import analysis, build_ads, cases, model, project_config
except ImportError:
    import analysis, build_ads, cases, model, project_config

from keysight.ads import de, dataset
from keysight.edatoolbox import ads


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n",
                          encoding="utf-8", newline="\n")


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_files():
    configuration = project_config.load_project()
    files = {p.name: p for p in sorted(configuration["paths"]["tools"].glob("*.py"))}
    files["project.toml"] = configuration["project_root"] / "project.toml"
    return files


def source_hashes():
    return {name: sha(path) for name, path in source_files().items()}


def snapshot_sources(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name, source in source_files().items():
        shutil.copyfile(source, destination / name)


def prepare(root):
    root=Path(root)
    root.mkdir(parents=True, exist_ok=False)
    (root/"cases").mkdir()
    rows=cases.requests()
    write_json(root/"requests.json", {"requests":rows,"e9_repetitions":cases.repetition_requests(rows)})
    write_json(root/"study_checks.json", {"e1_complete":False,"e8_complete":False,"e9_complete":False,
        "evidence_manifest_complete":False,"pre_run_predictions_complete":True})
    write_json(root/"study-settings.json", {"created_utc":utc(),"task_version":model.TASK_VERSION,
        "baseline_commit":model.BASELINE_COMMIT,"source_hashes":source_hashes(),
        "initial_requests":len(rows),"initial_unique_cases":len(cases.unique_cases(rows)),
        "scope":"synthetic fixed RLC research; no PDK capability or official benchmark claim",
        "research_choices":"Execute revision-1 proposed axes and numerical tolerances as declared synthetic assumptions",
        "optional_retuning":"not requested; required untuned study first",
        "project_manifest_sha256":sha(project_config.load_project()["project_root"] / "project.toml")})
    predictions={
        "E0":"The recovered ideal network should reproduce the pinned baseline and all four limits.",
        "E1":"RL-branch Q differs from terminal Q; Cp shifts actual SRF with finite Rs. Capacitor ESL reverses reactance above series resonance.",
        "E2":"Fixed Rs reduces DC transmission; common Q below 35.5919744144 cannot meet strict DC matching. RF current concentration can impose a stronger bound.",
        "E3":"Terminal Cp increases effective inductance below its tuning frequency and moves reflection extrema before reactance reverses.",
        "E4":"ESR dissipates stored energy and may damp reflection while increasing insertion loss; ESL shifts the effective shunt susceptance and can create resonances.",
        "E5":"Single-element changes break symmetry and can switch the worst reflection peak. Common scales shift frequency response nonlinearly.",
        "E6":"Loss and reactive shifts interact; satisfying DC and remaining inductive at 80GHz are necessary diagnostics, not sufficient system acceptance.",
        "E7":"Frozen Rs/Cp/ESR/ESL make value perturbations change actual Q/SRF. Ideal sensitivity rankings need not persist.",
        "E8":"Each one-coordinate slice may have multiple feasible windows. Retain all local brackets; do not infer a global monotone threshold.",
        "E9":"Fresh workspaces with frozen source and sweep lists should reproduce complex S within 1e-6 and frequencies within 1Hz."}
    write_json(root/"pre-run-predictions.json", {"recorded_utc":utc(),"predictions":predictions,
        "sequence":"Question -> Physical Model -> Prediction -> ADS Simulation -> Observation -> Explanation -> Design Decision"})
    return {"root":str(root),"requests":len(rows),"unique":len(cases.unique_cases(rows))}


def planned_sweeps(pred):
    sweeps=[("SP_broad",1e6,120e9,2401),("SP_passband",1e6,65e9,1301),
            ("SP_checkpoints",65e9,80e9,2)]
    for i,frequency in enumerate(pred["extrema_hz"]):
        if abs(frequency-65e9)<=1:
            start,stop,points=frequency-400e3,frequency,5
        else:
            # Supplementary positive-frequency points may extend below the
            # baseline 1MHz grid; preserve the true centered 100kHz spacing.
            start,stop,points=frequency-400e3,frequency+400e3,9
        sweeps.append((f"SP_root{i}",start,stop,points))
    return sweeps


def _native_snapshot(workspace, destination):
    workspace=Path(workspace);destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    for p in workspace.rglob("*"):
        if not p.is_file():continue
        rel=p.relative_to(workspace)
        if any(x in {"simulation","data","__pycache__"} for x in rel.parts):continue
        if ".cdslck" in p.name or p.name.startswith(".ads_lock") or p.suffix==".prf":continue
        if p.name in {"logFile.txt","saved.wrkstate"} or p.name.startswith("netlist.log"):continue
        if p.suffix not in {".oa",".tag",".views",".defs",".lib",".json",".cfg"} and p.name!=".oalib":continue
        target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)


def _check_netlist(netlist, manifest):
    import re
    if not re.search(r"define\s+inp_lpf\s*\(\s*rfin\s+rfout\s+gnd\s*\)",netlist):
        raise ValueError("Generated DUT terminal signature differs")
    for element in manifest["elements"]:
        name=element["name"];kind=element["kind"]
        line=next((line for line in netlist.splitlines() if line.startswith(f"{kind}:{name} ")),None)
        if not line:raise ValueError(f"Missing native primitive {name}")
        match=re.search(rf"\b{kind}=([^ ]+) ",line)
        if not match or float(match.group(1))!=element["value_si"]:
            raise ValueError(f"Native coefficient mismatch: {name}")
        expected=( [("R",element["rs_ohm"])] if kind=="L" else [])
        for key,value in expected:
            match=re.search(rf"\b{key}=([^ ]+) ",line)
            if not match or float(match.group(1))!=value:raise ValueError(f"Native Rs mismatch: {name}")
        for suffix,pk,modelkind in (("Cp","cp_f","C"),("ESR","esr_ohm","R"),("ESL","esl_h","L")):
            value=element.get(pk,0)
            branch=next((l for l in netlist.splitlines() if l.startswith(f"{modelkind}:{name}_{suffix} ")),None)
            if bool(branch)!=bool(value):raise ValueError(f"Zero/nonzero branch mismatch: {name}_{suffix}")
            if value and float(re.search(rf"\b{modelkind}=([^ ]+) ",branch).group(1))!=value:
                raise ValueError(f"Parasitic coefficient mismatch: {name}_{suffix}")
    body=netlist.split("define inp_lpf",1)[1].split("end inp_lpf",1)[0]
    primitives={}
    for line in body.splitlines():
        tokens=line.split()
        if tokens and re.match(r"^[RLC]:",tokens[0]):primitives[tokens[0].split(":",1)[1]]=tokens[1:3]
    expected_names=set();internal=[]
    ladder=["rfin","n1","n2","n3","n4","rfout"]
    for element in manifest["elements"]:
        name=element["name"];number=int(name[1:])
        if element["kind"]=="L":
            expected={ladder[number-1],ladder[number]}
            if set(primitives[name])!=expected:raise ValueError(f"Native series-arm connection mismatch: {name}")
            expected_names.add(name)
            if element["cp_f"]:
                if set(primitives[name+"_Cp"])!=expected:raise ValueError(f"Cp does not span arm terminals: {name}")
                expected_names.add(name+"_Cp")
        else:
            cursor=ladder[number]
            chain=([name+"_ESR"] if element["esr_ohm"] else [])+([name+"_ESL"] if element["esl_h"] else [])+[name]
            for i,part in enumerate(chain):
                nodes=primitives[part]
                if cursor not in nodes or nodes[0]==nodes[1]:raise ValueError(f"Disconnected/shorted shunt chain: {part}")
                cursor=nodes[1] if nodes[0]==cursor else nodes[0]
                expected_names.add(part)
                if i<len(chain)-1:
                    if cursor in ladder+["gnd"]:raise ValueError(f"Shunt series node shorts a ladder terminal: {part}")
                    internal.append(cursor)
            if cursor!="gnd":raise ValueError(f"Shunt chain return mismatch: {name}")
    if len(internal)!=len(set(internal)) or set(primitives)!=expected_names:
        raise ValueError("Unexpected/shared internal shunt node or extra DUT primitives")
    for number,node in ((1,"rfin"),(2,"rfout")):
        line=next((l for l in netlist.splitlines() if l.startswith(f"Port:Term{number} ")),"")
        if line.split()[1:3]!=[node,"0"] or "Z=50 Ohm" not in line:raise ValueError("External port ownership/reference mismatch")
    return {"ok":True,"method":"native signature, exact literal coefficients, every DUT arm/series node, and external 50-ohm port audit"}


def _export(output, cell="inp_lpf_sp", ports=2):
    data=dataset.open(Path(output)/f"{cell}.ds")
    rows=[];analyses={}
    for key in data:
        if not str(key).endswith(".SP"):continue
        frame=data[key].to_dataframe().reset_index()
        cols={str(c).replace("[","(").replace("]",")"):c for c in frame.columns}
        names=["S(1,1)","S(2,1)","S(1,2)","S(2,2)"] if ports==2 else ["S(1,1)"]
        if "freq" not in cols or any(n not in cols for n in names):raise ValueError(f"Unexpected dataset columns: {list(frame.columns)}")
        current=[]
        for _,row in frame.iterrows():
            f=float(row[cols["freq"]]);values=[f]
            for n in names:
                v=complex(row[cols[n]]);values.extend([v.real,v.imag])
            current.append(values)
        analyses[str(key)]=current;rows.extend(current)
    if not rows:raise ValueError("No ADS SP dataset data")
    unique={}
    for row in sorted(rows,key=lambda r:r[0]):
        if not np.isfinite(row).all():raise ValueError("Nonfinite ADS export")
        if row[0] in unique and max(abs(np.array(row[1:])-np.array(unique[row[0]][1:])))>1e-8:
            raise ValueError("Conflicting duplicate ADS export")
        unique[row[0]]=row
    header=analysis.FIELDS if ports==2 else ["freq_hz","s11_real","s11_imag"]
    def save(path,values):
        with Path(path).open("w",encoding="utf-8",newline="") as stream:
            writer=csv.writer(stream);writer.writerow(header);writer.writerows(values)
    save(Path(output)/"ads_sparameters.csv",unique.values())
    write_json(Path(output)/"dataset-analysis-counts.json",{k:len(v) for k,v in analyses.items()})
    return analyses


def _settings(manifest,sweeps,netlist,cell):
    return {"created_utc":utc(),"task_version":model.TASK_VERSION,"baseline_commit":model.BASELINE_COMMIT,
        "testbench":f"{build_ads.LIBRARY}:{cell}:schematic","ordered_ports":["rfin","rfout","gnd"],
        "reference_impedance_ohm":50,"temperature_deg_c":25,"temperature_law":"none; metadata only; no native temperature sweep or physical temperature claim",
        "ads_product_version":de.product_version().strip(),"ads_python_package_version":str(de.__version__),
        "python_version":sys.version,"numpy_version":np.__version__,"source_hashes":source_hashes(),
        "physical_sha256":model.physical_hash(manifest),"netlist_sha256":hashlib.sha256(netlist.encode()).hexdigest(),
        "sweeps":[{"analysis":n,"start_hz":a,"stop_hz":b,"points":c} for n,a,b,c in sweeps],
        "refinement_policy":"Three predeclared nested local grids evaluated in one invocation; measured subset spacing 400/200/100kHz, shared exact rational stationary points"}


def run_case(root,row,workspace,*,frozen_sweeps=None,case_folder=None):
    root=Path(root);workspace=Path(workspace)
    destination=root/(case_folder or "cases")/(row["request_id"] if row["family"]=="E9" else row["case_id"])
    destination.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();manifest=row["manifest"]
    write_json(destination/"manifest.json",manifest);write_json(destination/"request.json",row)
    try:
        pred=analysis.predict(manifest)
        write_json(destination/"prediction.json",dict(pred,recorded_utc=utc(),phase="before ADS simulation"))
        sweeps=planned_sweeps(pred) if frozen_sweeps is None else frozen_sweeps
        try:
            if not de.workspace_is_open() or Path(de.active_workspace().path).resolve()!=workspace.resolve():
                raise RuntimeError("Requested workspace must be activated before native value updates")
            tb=build_ads.update_values(manifest,sweeps)
        except (RuntimeError,ValueError):
            tb=build_ads.build(workspace,manifest,sweeps,overwrite=(workspace/build_ads.LIBRARY/"inp_lpf").exists())
        netlist=tb.generate_netlist()
        audit=_check_netlist(netlist,manifest)
        (destination/"schematic.net").write_text(netlist,encoding="utf-8",newline="\n")
        settings=_settings(manifest,sweeps,netlist,"inp_lpf_sp")
        settings["netlist_saved_bytes_sha256"]=sha(destination/"schematic.net")
        settings["native_audit"]=audit
        write_json(destination/"settings.json",settings)
        inputs=destination/"source-inputs";inputs.mkdir()
        snapshot_sources(inputs)
        _native_snapshot(workspace,inputs/"native")
        ads.CircuitSimulator().run_netlist(netlist,output_dir=str(destination))
        analyses=_export(destination)
        f,s=analysis.read_csv(destination/"ads_sparameters.csv")
        analysis.export_touchstone(destination/"inp_lpf.s2p",f,s)
        history=[]
        for round_index,spacing in enumerate((400e3,200e3,100e3)):
            selected=[]
            for name,values in analyses.items():
                if "SP_root" not in name:selected.extend(values);continue
                values=np.asarray(values)
                # Nested grid phases share the predicted center exactly.
                center=(values[0,0]+values[-1,0])/2
                if abs(values[-1,0]-65e9)<=1:center=65e9
                ids=np.flatnonzero(abs((values[:,0]-center)/spacing-np.rint((values[:,0]-center)/spacing))<1e-5)
                selected.extend(values[ids].tolist())
            selected=np.asarray(sorted({r[0]:r for r in selected}.values(),key=lambda r:r[0]))
            rf=selected[:,0];rs=np.empty((len(rf),2,2),complex)
            for col,o,i in ((1,0,0),(3,1,0),(5,0,1),(7,1,1)):rs[:,o,i]=selected[:,col]+1j*selected[:,col+1]
            h=analysis.measured_round(rf,rs,pred,spacing)
            csvpath=destination/f"refinement-round-{round_index}.csv"
            with csvpath.open("w",encoding="utf-8",newline="") as stream:
                writer=csv.writer(stream);writer.writerow(analysis.FIELDS);writer.writerows(selected)
            h["source_csv"]=csvpath.name;history.append(h)
        write_json(destination/"refinement-history.json",history)
        result=analysis.verify(f,s,manifest,prediction=pred,refinement_history=history)
        result.update({"case_id":row["case_id"],"request_id":row["request_id"],"family":row["family"],
                       "completed_utc":utc(),"elapsed_seconds":time.monotonic()-start})
        write_json(destination/"summary.json",result)
        return {"case_id":row["case_id"],"state":result["state"],"coverage":result.get("coverage",{}).get("continuous_band_justified"),
                "elapsed_seconds":result["elapsed_seconds"],"metrics":{k:v.get("value_db") for k,v in result.get("metrics",{}).items()}}
    except Exception as exc:
        import traceback
        write_json(destination/"failed-attempt.json",{"created_utc":utc(),"error":repr(exc),"traceback":traceback.format_exc()})
        raise


def batch(root,workspace,*,limit=5,families=None):
    root=Path(root);rows=json.loads((root/"requests.json").read_text())["requests"]
    result=[]
    for row in cases.unique_cases(rows):
        if families and row["family"] not in families:continue
        target=root/"cases"/row["case_id"]
        if (target/"summary.json").exists():continue
        if target.exists():raise RuntimeError(f"Preserved unfinished attempt requires diagnosis: {row['case_id']}")
        result.append(run_case(root,row,workspace))
        if len(result)>=limit:break
    return result
