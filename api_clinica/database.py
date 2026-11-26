"""Camada de acesso a dados: conexão SQLite, inicialização e carga inicial (seed)."""
import os
import sqlite3
from contextlib import contextmanager

from flask import g
from werkzeug.security import generate_password_hash

import config

SCHEMA_PATH = os.path.join(config.BASE_DIR, "db", "schema.sql")


def _connect():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=15, isolation_level=None)  # autocommit; transações explícitas
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def get_db():
    """Conexão por requisição HTTP (Flask g)."""
    if "db" not in g:
        g.db = _connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def conexao_avulsa():
    """Conexão fora do contexto HTTP (ex.: worker de reenvio)."""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transacao(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def row(r):
    return dict(r) if r is not None else None


def rows(rs):
    return [dict(r) for r in rs]


# ---------------------------------------------------------------------
# Inicialização + dados fictícios
# ---------------------------------------------------------------------
def init_db(com_seed=True):
    conn = _connect()
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    if com_seed and conn.execute("SELECT COUNT(*) FROM especie").fetchone()[0] == 0:
        _seed(conn)
    conn.close()


def _seed(conn):
    conn.execute("BEGIN")
    especies = [
        ("Cão", "Canis lupus familiaris"),
        ("Gato", "Felis catus"),
        ("Ave", "Aves domésticas e silvestres legalizadas"),
    ]
    conn.executemany("INSERT INTO especie (nome, descricao) VALUES (?, ?)", especies)
    racas = [
        ("Labrador Retriever", "Porte grande", 1), ("Poodle", "Porte pequeno/médio", 1),
        ("Golden Retriever", "Porte grande", 1), ("Shih Tzu", "Porte pequeno", 1),
        ("Bulldog Francês", "Porte pequeno", 1), ("Vira-lata (SRD)", "Sem raça definida", 1),
        ("Siamês", "Pelagem curta", 2), ("Persa", "Pelagem longa", 2),
        ("Maine Coon", "Porte grande", 2), ("Sem raça definida (SRD)", "Sem raça definida", 2),
        ("Calopsita", "Psitacídeo", 3), ("Periquito-australiano", "Psitacídeo", 3),
        ("Canário", "Passeriforme", 3),
    ]
    conn.executemany("INSERT INTO raca (nome, descricao, especie_id) VALUES (?, ?, ?)", racas)

    senha = generate_password_hash("Senha@123")
    vets = [
        # nome, cpf, crmv, uf, email, telefone, confirmada, situacao
        ("Dra. Ana Souza", "52998224725", "12345", "RJ", "ana@clinica.vet", "21999990001", 1, "ATIVO"),
        ("Dr. Bruno Lima", "39053344705", "23456", "RJ", "bruno@clinica.vet", "21999990002", 1, "INATIVO"),
        ("Dra. Carla Mendes", "24681357928", "34567", "RJ", "carla@clinica.vet", "21999990003", 0, "ATIVO"),
    ]
    for v in vets:
        conn.execute(
            """INSERT INTO veterinario (nome, cpf, crmv, crmv_uf, email, telefone, senha_hash,
                   senha_confirmada, data_confirmacao, situacao)
               VALUES (?,?,?,?,?,?,?,?, CASE WHEN ? = 1 THEN datetime('now','localtime') END, ?)""",
            (v[0], v[1], v[2], v[3], v[4], v[5], senha, v[6], v[6], v[7]),
        )

    # Endereço da clínica (fictício)
    conn.execute(
        """INSERT INTO endereco (cep, logradouro, numero, complemento, bairro, cidade, uf, codigo_ibge, tipo)
           VALUES ('22775040','Avenida Embaixador Abelardo Bueno','1000','Loja 10','Barra da Tijuca',
                   'Rio de Janeiro','RJ','3304557','CLINICA')"""
    )
    # Tutor e animal de exemplo
    cur = conn.execute(
        """INSERT INTO endereco (cep, logradouro, numero, complemento, bairro, cidade, uf, codigo_ibge)
           VALUES ('22750009','Estrada dos Bandeirantes','250','Casa 2','Taquara','Rio de Janeiro','RJ','3304557')"""
    )
    end_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO tutor (nome, cpf, data_nascimento, email, telefone, endereco_id)
           VALUES ('Mariana Oliveira (fictícia)','12345678909','1990-05-12','mariana@exemplo.com','21988887777',?)""",
        (end_id,),
    )
    tutor_id = cur.lastrowid
    conn.execute(
        """INSERT INTO animal (nome, data_nascimento, sexo, cor, peso_atual, tutor_id, especie_id, raca_id)
           VALUES ('Thor', '2021-03-10', 'M', 'Caramelo', 28.5, ?, 1, 1)""",
        (tutor_id,),
    )
    conn.execute(
        """INSERT INTO animal (nome, idade_estimada_meses, sexo, cor, peso_atual, tutor_id, especie_id, raca_id)
           VALUES ('Mia', 18, 'F', 'Branca e cinza', 4.2, ?, 2, NULL)""",
        (tutor_id,),
    )
    conn.execute("COMMIT")


if __name__ == "__main__":
    init_db()
    print(f"Banco da clínica inicializado em {config.DB_PATH}")
