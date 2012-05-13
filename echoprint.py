import json
import os
import subprocess

import fingerprint
import db
import sqlalchemy
import conf

import echoprint_support.fp
import echoprint_support.solr

if not conf.conf.has_section("echoprint"):
    raise Exception("No echoprint configuration section present")

s = conf.conf.get("echoprint", "solr_server")
th = conf.conf.get("echoprint", "tyrant_host")
tp = conf.conf.getint("echoprint", "tyrant_port")
echoprint_support.fp._fp_solr = echoprint_support.solr.SolrConnectionPool(s)
echoprint_support.fp._tyrant_address = [th, tp]

codegen_path = conf.conf.get("echoprint", "codegen_path")

class EchoprintModel(db.Base):
    __tablename__ = "echoprint"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    file_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('file.id'))
    trid = sqlalchemy.Column(sqlalchemy.String)

    def __init__(self, file, trid):
        self.file_id = file.id
        self.trid = trid

    def __repr__(self):
        return "Echoprint<%s, id=%s>" % (self.file_id, self.trid)

class Echoprint(fingerprint.Fingerprinter):

    def fingerprint(self, file):
        data = self._codegen(file)
        trid = echoprint_support.fp.new_track_id()
        data = data[0]
        ret = {}
        ret["track_id"] = trid
        if "code" in data:
            ret["fp"] = echoprint_support.fp.decode_code_string(data["code"])
            ret["codever"] = data["metadata"]["version"]
            ret.update(data["metadata"])
            ret["length"] = ret["duration"]
        else:
            ret["error"] = data

        return (trid, ret)

    def _codegen(self, file, start=-1, duration=-1):
        proclist = [codegen_path, os.path.abspath(file)]
        if start > 0:
            proclist.append("%d" % start)
        if duration > 0:
            proclist.append("%d" % duration)
        p = subprocess.Popen(proclist, stdout=subprocess.PIPE)
        code = p.communicate()[0]
        return json.loads(code)

    def ingest_single(self, data):
        echoprint_support.fp.ingest(data, do_commit=True)

    def ingest_many(self, data):
        # echoprint ingest will take a list then commit
        echoprint_support.fp.ingest(data, do_commit=True)

    def lookup(self, file):
        data = self._codegen(file)
        code = data[0]["code"]
        match = echoprint_support.fp.best_match_for_query(code)
        return match.TRID

    def delete_all(self):
        # Erase solr and tokyo tyrant
        echoprint_support.fp.erase_database(True)
        # Erase the local database
        db.session.query(EchoprintModel).delete()
        db.session.commit()

fingerprint.fingerprint_index["echoprint"] = {
    "dbmodel": EchoprintModel,
    "instance": Echoprint
}

db.create_tables()

