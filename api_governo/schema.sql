-- =====================================================================
-- API GOVERNAMENTAL SIMULADA - Registro de animais com microchip
-- Banco PRÓPRIO e SEPARADO do banco da clínica (governo.db).
-- ATENÇÃO: serviço fictício para fins acadêmicos. Não representa
-- nenhuma integração oficial com sistemas governamentais reais.
-- =====================================================================
PRAGMA foreign_keys = ON;

-- Animais registrados no "cadastro nacional" simulado
CREATE TABLE IF NOT EXISTS animal_registro (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    microchip           CHAR(15)     NOT NULL UNIQUE,
    nome                VARCHAR(100) NOT NULL,
    especie             VARCHAR(60)  NOT NULL,
    raca                VARCHAR(80),
    sexo                CHAR(1)      NOT NULL CHECK (sexo IN ('M','F')),
    data_nascimento     DATE,
    cor                 VARCHAR(60),
    tutor_nome          VARCHAR(150) NOT NULL,
    tutor_cpf           CHAR(11)     NOT NULL,
    tutor_municipio_ibge CHAR(7),
    veterinario_crmv    VARCHAR(10)  NOT NULL,
    veterinario_crmv_uf CHAR(2)      NOT NULL,
    origem_sistema      VARCHAR(60)  NOT NULL,
    id_animal_origem    VARCHAR(40)  NOT NULL,
    microchip_anterior  CHAR(15),
    situacao            VARCHAR(15)  NOT NULL DEFAULT 'ATIVO' CHECK (situacao IN ('ATIVO','SUBSTITUIDO')),
    cadastro_implicito  INTEGER      NOT NULL DEFAULT 0,   -- 1 = criado a partir de comunicação de vacina
    criado_em           DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    atualizado_em       DATETIME     NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Vacinações antirrábicas comunicadas
CREATE TABLE IF NOT EXISTS vacinacao_antirrabica (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_registro_id  INTEGER      NOT NULL REFERENCES animal_registro(id),
    microchip           CHAR(15)     NOT NULL,
    origem_sistema      VARCHAR(60)  NOT NULL,
    id_aplicacao_origem VARCHAR(40)  NOT NULL,
    data_aplicacao      DATE         NOT NULL,
    vacina_nome         VARCHAR(100) NOT NULL,
    fabricante          VARCHAR(100) NOT NULL,
    lote                VARCHAR(40)  NOT NULL,
    veterinario_nome    VARCHAR(150) NOT NULL,
    veterinario_crmv    VARCHAR(10)  NOT NULL,
    veterinario_crmv_uf CHAR(2)      NOT NULL,
    protocolo           VARCHAR(40)  NOT NULL,
    recebido_em         DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    -- 2ª barreira contra duplicidade (além da chave de idempotência)
    UNIQUE (origem_sistema, id_aplicacao_origem)
);

-- Operações processadas (protocolos + idempotência)
CREATE TABLE IF NOT EXISTS operacao (
    protocolo           VARCHAR(40)  PRIMARY KEY,
    tipo                VARCHAR(30)  NOT NULL,
    chave_idempotencia  VARCHAR(80)  UNIQUE,
    microchip           CHAR(15),
    status              VARCHAR(12)  NOT NULL CHECK (status IN ('PROCESSADA','REJEITADA')),
    http_status         INTEGER      NOT NULL,
    mensagem            TEXT,
    payload             TEXT,
    resposta            TEXT,
    recebida_em         DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    replays             INTEGER      NOT NULL DEFAULT 0
);

-- Configuração da simulação de falhas (linha única)
CREATE TABLE IF NOT EXISTS simulacao (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    modo                VARCHAR(20)  NOT NULL DEFAULT 'NORMAL'
                        CHECK (modo IN ('NORMAL','INDISPONIVEL','LENTO','ERRO_INTERMITENTE')),
    atraso_segundos     INTEGER      NOT NULL DEFAULT 10,
    atualizado_em       DATETIME     NOT NULL DEFAULT (datetime('now','localtime'))
);
INSERT OR IGNORE INTO simulacao (id, modo) VALUES (1, 'NORMAL');
