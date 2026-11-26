-- =====================================================================
-- SDM - Sistema de Gestão de Clínica Veterinária
-- Banco de dados da CLÍNICA (API privada)
-- SGBD: SQLite 3 (relacional). Compatível com PostgreSQL com ajustes
-- mínimos de tipos (INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL).
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. ENDERECO
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS endereco (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cep             CHAR(8)      NOT NULL CHECK (length(cep) = 8),
    logradouro      VARCHAR(150) NOT NULL,
    numero          VARCHAR(20)  NOT NULL,
    complemento     VARCHAR(100),
    bairro          VARCHAR(100) NOT NULL,
    cidade          VARCHAR(100) NOT NULL,
    uf              CHAR(2)      NOT NULL CHECK (length(uf) = 2),
    codigo_ibge     CHAR(7),
    tipo            VARCHAR(10)  NOT NULL DEFAULT 'TUTOR' CHECK (tipo IN ('TUTOR','CLINICA'))
);

-- ---------------------------------------------------------------------
-- 2. TUTOR
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tutor (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            VARCHAR(150) NOT NULL,
    cpf             CHAR(11)     NOT NULL UNIQUE,
    data_nascimento DATE         NOT NULL,
    email           VARCHAR(150) NOT NULL,
    telefone        VARCHAR(20)  NOT NULL,
    endereco_id     INTEGER      NOT NULL REFERENCES endereco(id),
    data_cadastro   DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    situacao        VARCHAR(10)  NOT NULL DEFAULT 'ATIVO' CHECK (situacao IN ('ATIVO','INATIVO'))
);

-- ---------------------------------------------------------------------
-- 3. ESPECIE
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS especie (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            VARCHAR(60)  NOT NULL UNIQUE,
    descricao       VARCHAR(255),
    situacao        VARCHAR(10)  NOT NULL DEFAULT 'ATIVO' CHECK (situacao IN ('ATIVO','INATIVO'))
);

-- ---------------------------------------------------------------------
-- 4. RACA (sempre associada a uma espécie)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raca (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            VARCHAR(80)  NOT NULL,
    descricao       VARCHAR(255),
    especie_id      INTEGER      NOT NULL REFERENCES especie(id),
    situacao        VARCHAR(10)  NOT NULL DEFAULT 'ATIVO' CHECK (situacao IN ('ATIVO','INATIVO')),
    UNIQUE (nome, especie_id),
    UNIQUE (id, especie_id)          -- permite FK composta (raca, especie) em ANIMAL
);

-- ---------------------------------------------------------------------
-- 5. VETERINARIO (usuários do sistema)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS veterinario (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                 VARCHAR(150) NOT NULL,
    cpf                  CHAR(11)     NOT NULL UNIQUE,
    crmv                 VARCHAR(10)  NOT NULL,
    crmv_uf              CHAR(2)      NOT NULL,
    email                VARCHAR(150) NOT NULL UNIQUE,
    telefone             VARCHAR(20)  NOT NULL,
    senha_hash           VARCHAR(255) NOT NULL,           -- PBKDF2/scrypt (werkzeug), nunca texto puro
    senha_confirmada     INTEGER      NOT NULL DEFAULT 0 CHECK (senha_confirmada IN (0,1)),
    data_confirmacao     DATETIME,
    codigo_confirmacao_hash VARCHAR(255),                 -- código de 6 dígitos (hash)
    codigo_expira_em     DATETIME,
    data_cadastro        DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    situacao             VARCHAR(10)  NOT NULL DEFAULT 'ATIVO' CHECK (situacao IN ('ATIVO','INATIVO')),
    ultimo_acesso        DATETIME,
    UNIQUE (crmv, crmv_uf)
);

-- Sessões (para logout/revogação de token)
CREATE TABLE IF NOT EXISTS sessao (
    id              VARCHAR(64)  PRIMARY KEY,
    veterinario_id  INTEGER      NOT NULL REFERENCES veterinario(id),
    criada_em       DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    expira_em       DATETIME     NOT NULL,
    encerrada_em    DATETIME
);

-- Caixa de saída de e-mails (envio SIMULADO para fins acadêmicos)
CREATE TABLE IF NOT EXISTS email_simulado (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    destinatario    VARCHAR(150) NOT NULL,
    assunto         VARCHAR(200) NOT NULL,
    corpo           TEXT         NOT NULL,
    enviado_em      DATETIME     NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ---------------------------------------------------------------------
-- 6. ANIMAL
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS animal (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                VARCHAR(100) NOT NULL,
    data_nascimento     DATE,
    idade_estimada_meses INTEGER CHECK (idade_estimada_meses IS NULL OR idade_estimada_meses >= 0),
    sexo                CHAR(1)      NOT NULL CHECK (sexo IN ('M','F')),
    cor                 VARCHAR(60)  NOT NULL,
    peso_atual          REAL         NOT NULL CHECK (peso_atual > 0),
    tutor_id            INTEGER      NOT NULL REFERENCES tutor(id),
    especie_id          INTEGER      NOT NULL REFERENCES especie(id),
    raca_id             INTEGER,                         -- NULL = sem raça definida
    microchip_atual     CHAR(15)     UNIQUE,             -- cópia do vínculo ativo (consulta rápida)
    situacao            VARCHAR(10)  NOT NULL DEFAULT 'ATIVO' CHECK (situacao IN ('ATIVO','INATIVO','OBITO')),
    gov_situacao        VARCHAR(15)  NOT NULL DEFAULT 'NAO_ENVIADO'
                        CHECK (gov_situacao IN ('NAO_ENVIADO','PENDENTE','SINCRONIZADO','FALHA')),
    gov_protocolo       VARCHAR(40),
    gov_ultima_sync     DATETIME,
    data_cadastro       DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK (data_nascimento IS NOT NULL OR idade_estimada_meses IS NOT NULL),
    -- garante que a raça pertence à espécie informada
    FOREIGN KEY (raca_id, especie_id) REFERENCES raca(id, especie_id)
);

-- ---------------------------------------------------------------------
-- 7. VINCULO_MICROCHIP (histórico de vinculação e substituição)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vinculo_microchip (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id           INTEGER      NOT NULL REFERENCES animal(id),
    codigo_microchip    CHAR(15)     NOT NULL UNIQUE,    -- um chip nunca é reutilizado
    veterinario_id      INTEGER      NOT NULL REFERENCES veterinario(id),
    data_implantacao    DATE         NOT NULL,
    data_vinculo        DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    ativo               INTEGER      NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),
    data_desativacao    DATETIME,
    motivo_substituicao VARCHAR(255),
    substituido_por_id  INTEGER REFERENCES vinculo_microchip(id)
);
-- no máximo um vínculo ativo por animal
CREATE UNIQUE INDEX IF NOT EXISTS ux_vinculo_ativo_por_animal
    ON vinculo_microchip(animal_id) WHERE ativo = 1;

-- ---------------------------------------------------------------------
-- 8. CONSULTA
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consulta (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id           INTEGER      NOT NULL REFERENCES animal(id),
    veterinario_id      INTEGER      NOT NULL REFERENCES veterinario(id),
    data_hora           DATETIME     NOT NULL,
    motivo              VARCHAR(255) NOT NULL,
    anamnese            TEXT,
    sintomas            TEXT,
    diagnostico         TEXT,
    tratamento          TEXT,
    prescricao          TEXT,
    peso_registrado     REAL CHECK (peso_registrado IS NULL OR peso_registrado > 0),
    temperatura         REAL CHECK (temperatura IS NULL OR temperatura BETWEEN 30 AND 45),
    observacoes         TEXT,
    situacao            VARCHAR(15)  NOT NULL DEFAULT 'AGENDADA'
                        CHECK (situacao IN ('AGENDADA','REALIZADA','CANCELADA','NAO_COMPARECEU')),
    criada_em           DATETIME     NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ---------------------------------------------------------------------
-- 9. VACINA (aplicações de vacina)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vacina (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id           INTEGER      NOT NULL REFERENCES animal(id),
    veterinario_id      INTEGER      NOT NULL REFERENCES veterinario(id),
    nome_vacina         VARCHAR(100) NOT NULL,
    -- classificação ESTRUTURADA (não depende do texto digitado)
    tipo_vacina         VARCHAR(20)  NOT NULL CHECK (tipo_vacina IN
                        ('ANTIRRABICA','POLIVALENTE_CANINA','POLIVALENTE_FELINA','GRIPE_CANINA',
                         'GIARDIASE','LEISHMANIOSE','LEUCEMIA_FELINA','OUTRA')),
    antirrabica         INTEGER      NOT NULL CHECK (antirrabica IN (0,1)),
    fabricante          VARCHAR(100) NOT NULL,
    lote                VARCHAR(40)  NOT NULL,
    data_aplicacao      DATE         NOT NULL,
    dose                VARCHAR(40)  NOT NULL,           -- ex.: '1ª dose', 'Reforço anual'
    via_aplicacao       VARCHAR(20)  NOT NULL CHECK (via_aplicacao IN ('SUBCUTANEA','INTRAMUSCULAR','INTRANASAL','ORAL')),
    data_proxima_dose   DATE,
    data_validade_lote  DATE         NOT NULL,
    observacoes         TEXT,
    situacao            VARCHAR(10)  NOT NULL DEFAULT 'APLICADA' CHECK (situacao IN ('AGENDADA','APLICADA','CANCELADA')),
    criada_em           DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK (antirrabica = (CASE WHEN tipo_vacina = 'ANTIRRABICA' THEN 1 ELSE 0 END)),
    CHECK (data_proxima_dose IS NULL OR data_proxima_dose > data_aplicacao)
);

-- ---------------------------------------------------------------------
-- 10. INTEGRACAO_GOVERNO (controle das operações com o serviço externo)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS integracao_governo (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id           INTEGER      NOT NULL REFERENCES animal(id),
    vacina_id           INTEGER      REFERENCES vacina(id),
    tipo_operacao       VARCHAR(25)  NOT NULL CHECK (tipo_operacao IN
                        ('CADASTRO_ANIMAL','ATUALIZACAO_ANIMAL','VACINACAO_ANTIRRABICA')),
    protocolo_externo   VARCHAR(40),
    chave_idempotencia  VARCHAR(80)  NOT NULL UNIQUE,
    situacao            VARCHAR(12)  NOT NULL DEFAULT 'PENDENTE'
                        CHECK (situacao IN ('PENDENTE','ENVIADA','CONFIRMADA','FALHA')),
    data_solicitacao    DATETIME     NOT NULL DEFAULT (datetime('now','localtime')),
    data_ultimo_envio   DATETIME,
    data_resposta       DATETIME,
    proxima_tentativa   DATETIME,
    tentativas          INTEGER      NOT NULL DEFAULT 0,
    http_status         INTEGER,
    mensagem_erro       TEXT,
    payload             TEXT         NOT NULL,           -- JSON enviado (reutilizado nos reenvios)
    resposta            TEXT,                            -- JSON recebido
    CHECK (tipo_operacao <> 'VACINACAO_ANTIRRABICA' OR vacina_id IS NOT NULL)
);
-- uma única comunicação obrigatória por aplicação de vacina
CREATE UNIQUE INDEX IF NOT EXISTS ux_integracao_vacina
    ON integracao_governo(vacina_id) WHERE vacina_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_animal_tutor      ON animal(tutor_id);
CREATE INDEX IF NOT EXISTS ix_consulta_animal   ON consulta(animal_id, data_hora);
CREATE INDEX IF NOT EXISTS ix_vacina_animal     ON vacina(animal_id, data_aplicacao);
CREATE INDEX IF NOT EXISTS ix_vacina_proxima    ON vacina(data_proxima_dose);
CREATE INDEX IF NOT EXISTS ix_integracao_sit    ON integracao_governo(situacao, proxima_tentativa);
