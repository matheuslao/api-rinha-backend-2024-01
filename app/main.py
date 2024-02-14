import os, time

from datetime import datetime, timedelta
from fastapi import FastAPI, Body, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, select
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


Base = declarative_base()

class Transacao(BaseModel):
    valor: int
    tipo: str
    descricao: str

class Saldo(BaseModel):
    saldo: int
    limite: int

class TransacaoDB(Base):
    __tablename__ = 'transacoes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(Integer)
    valor = Column(Integer)
    tipo = Column(String)
    descricao = Column(String)
    realizada_em = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "valor": self.valor,
            "tipo": self.tipo,
            "descricao": self.descricao,
            "realizada_em": self.realizada_em.isoformat()
        }

class Cliente(Base):
    __tablename__ = 'clientes'
    id = Column(Integer, primary_key=True)
    limite = Column(Integer)
    saldo = Column(Integer)

app = FastAPI()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")

DB_URL = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'

def wait_for_db(db_url, max_attempts=10, delay=2):
    time.sleep(delay)
    for attempt in range(max_attempts):
        try:
            engine = create_engine(
                db_url, pool_size=40, max_overflow=10, 
                isolation_level="READ COMMITTED"
            )
            engine.connect()
            return engine
        except:
            time.sleep(delay)
    raise RuntimeError("Não foi possível conectar-se ao banco de dados após várias tentativas.")


engine = wait_for_db(DB_URL)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_cliente(db, id: int, op: str = "e"):

    #cliente = db.query(Cliente).filter(Cliente.id == id).first()

    if op == "e":
        cliente = db.query(Cliente).get(id)
    else:
        cliente = db.query(Cliente).filter(Cliente.id == id).with_for_update().first()

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente

@app.post("/clientes/{id}/transacoes")
async def registrar_transacao(id: int, transacao: Transacao = Body(...), db = Depends(get_db)):

    if transacao.tipo not in ("c", "d"):
        raise HTTPException(status_code=422, detail="Tipo de transação inválido")

    if transacao.valor <= 0:
        raise HTTPException(status_code=422, detail="Valor da transação inválido")

    if not transacao.descricao:
        raise HTTPException(status_code=422, detail="Descrição da transação é obrigatória")

    if len(transacao.descricao) < 1 or len(transacao.descricao) > 10:
        raise HTTPException(status_code=422, detail="Descrição da transação com tamanho errado")


    with db.begin() as trans:
        cliente = get_cliente(db, id, "t")
        if transacao.tipo == "d":
            saldo_provisorio = cliente.saldo - transacao.valor
            if saldo_provisorio < (-1 * cliente.limite):
                raise HTTPException(status_code=422, detail="Saldo insuficiente")
   
            cliente.saldo = Cliente.saldo - transacao.valor
        else:
            cliente.saldo = Cliente.saldo + transacao.valor
            
        nova_transacao = TransacaoDB(cliente_id=id, valor=transacao.valor, tipo=transacao.tipo, descricao=transacao.descricao)
        db.add(nova_transacao)
        try:
            trans.commit()
            #db.commit()
        except Exception as e:
            trans.rollback()
            raise e

    return Saldo(limite=cliente.limite, saldo=cliente.saldo)

@app.get("/clientes/{id}/extrato")
async def obter_extrato(id: int, db = Depends(get_db)):
    cliente = get_cliente(db, id)
    ultimas_transacoes = db.query(TransacaoDB).filter(TransacaoDB.cliente_id == id).order_by(TransacaoDB.realizada_em.desc()).limit(10).all()

    ultimas_transacoes_json = [transacao.to_dict() for transacao in ultimas_transacoes]

    return {
        "saldo": {
            "total": cliente.saldo,
            "data_extrato": datetime.now(),
            "limite": cliente.limite,
        },
        "ultimas_transacoes": ultimas_transacoes_json,
    }