# Relatório de Testes — SDM Clínica Veterinária

**Execução:** 25/11/2026 04:02:04  
**Ambiente:** API da clínica `http://127.0.0.1:5000` · API governamental simulada `http://127.0.0.1:5001`  
**Ferramenta:** script automatizado `tests/testes_obrigatorios.py` (Python + requests). A mesma sequência está na coleção Postman `tests/SDM_Clinica.postman_collection.json`.  
**Resultado geral:** 23 de 23 testes aprovados (16/16 obrigatórios, 7/7 complementares).

## Resumo

| # | Teste | Esperado | Resultado |
|---|---|---|---|
| 1 | Login de veterinário ativo e com senha confirmada | HTTP 200 com token Bearer | APROVADO |
| 2 | Bloqueio de veterinário inativo | HTTP 403 - veterinário inativo | APROVADO |
| 3 | Bloqueio de veterinário com senha não confirmada | HTTP 403 - senha não confirmada | APROVADO |
| 4 | Rejeição de senha incorreta | HTTP 401 - e-mail ou senha incorretos | APROVADO |
| 5 | Cadastro de tutor e validação de CPF duplicado | 201 no cadastro; 409 no CPF repetido; 422 CPF inválido | APROVADO |
| 6 | Consulta de CEP válido e tratamento de CEP inexistente | 200 com endereço preenchido; 404 CEP inexistente | APROVADO |
| 7 | Cadastro de animal e vínculo de microchip | 201; vínculo registra veterinário e data; animal sincronizado | APROVADO |
| 8 | Rejeição de microchip já utilizado | HTTP 409 | APROVADO |
| 9 | Registro de consulta e consulta ao histórico clínico | 201; consulta aparece no histórico do animal | APROVADO |
| 10 | Registro de vacina e consulta às próximas doses | 201; próxima dose listada | APROVADO |
| 11 | Cadastro e atualização de animal na API governamental simulada | Animal encontrado no serviço externo; atualização confirmada | APROVADO |
| 12 | Envio obrigatório de vacina antirrábica | Registro local + comunicação CONFIRMADA com protocolo, inclusive para animal ainda não cadastrado no serviço externo | APROVADO |
| 13 | Ausência de comunicação obrigatória para vacina não antirrábica | Nenhuma integração gerada | APROVADO |
| 14 | Indisponibilidade da API governamental e registro de pendência | Vacina registrada localmente; comunicação PENDENTE com erro e tentativa contabilizada | APROVADO |
| 15 | Reenvio de comunicação pendente e confirmação posterior | Após o retorno do serviço, reenvio confirma com protocolo | APROVADO |
| 16 | Repetição de solicitação sem duplicidade de vacinação no serviço externo | Mesmo protocolo; contagem inalterada | APROVADO |
| C1 | Proteção de endpoints sem autenticação | HTTP 401 | APROVADO |
| C2 | Raça incompatível com a espécie | HTTP 422 | APROVADO |
| C3 | Substituição de microchip preservando histórico | Novo chip ativo, anterior inativo com motivo | APROVADO |
| C4 | Cadastro de veterinário com confirmação de senha por código | 403 antes; 200 após confirmar | APROVADO |
| C5 | Logout encerra a sessão | token deixa de valer (401) | APROVADO |
| C6 | Antirrábica em animal sem microchip: registro local mantido e envio após o vínculo | FALHA aguardando microchip -> CONFIRMADA após vincular | APROVADO |
| C7 | Timeout com processamento tardio no serviço externo: reenvio reconhecido sem duplicar | PENDENTE por timeout -> reenvio CONFIRMADA (replay idempotente); 1 único registro externo | APROVADO |

## Evidências detalhadas

### 1. Login de veterinário ativo e com senha confirmada

*Esperado:* HTTP 200 com token Bearer  
*Resultado:* **APROVADO** (85 ms)

- [OK] POST /api/auth/login (ana@clinica.vet) -> HTTP 200
- [OK] token recebido (eyJzaWQiOiI1YTRlMj...), expira_em=2026-11-25 12:01:54
- [OK] GET /api/auth/me -> Dra. Ana Souza

### 2. Bloqueio de veterinário inativo

*Esperado:* HTTP 403 - veterinário inativo  
*Resultado:* **APROVADO** (80 ms)

- [OK] login bruno@clinica.vet (INATIVO) -> HTTP 403: Acesso bloqueado: veterinário inativo. Procure a administração da clínica.

### 3. Bloqueio de veterinário com senha não confirmada

*Esperado:* HTTP 403 - senha não confirmada  
*Resultado:* **APROVADO** (79 ms)

- [OK] login carla@clinica.vet (não confirmada) -> HTTP 403: Acesso bloqueado: senha ainda não confirmada. Use o código enviado ao seu e-mail.

### 4. Rejeição de senha incorreta

*Esperado:* HTTP 401 - e-mail ou senha incorretos  
*Resultado:* **APROVADO** (79 ms)

- [OK] login com senha errada -> HTTP 401: E-mail ou senha incorretos.

### 5. Cadastro de tutor e validação de CPF duplicado

*Esperado:* 201 no cadastro; 409 no CPF repetido; 422 CPF inválido  
*Resultado:* **APROVADO** (10 ms)

- [OK] POST /api/tutores (CPF 76665202550) -> HTTP 201, id=2
- [OK] POST /api/tutores com o mesmo CPF -> HTTP 409: Já existe um tutor cadastrado com este CPF.
- [OK] POST /api/tutores com CPF inválido -> HTTP 422: ['CPF inválido.']

### 6. Consulta de CEP válido e tratamento de CEP inexistente

*Esperado:* 200 com endereço preenchido; 404 CEP inexistente  
*Resultado:* **APROVADO** (11 ms)

- [OK] GET /api/cep/22775040 -> HTTP 200: Avenida Embaixador Abelardo Bueno, Barra da Tijuca, Rio de Janeiro/RJ, IBGE 3304557
- [OK] GET /api/cep/00000000 -> HTTP 404: CEP não encontrado.
- [OK] GET /api/cep/123 (formato inválido) -> HTTP 400: CEP deve conter 8 dígitos.
- Nota: Ambiente de execução sem acesso à internet: o ViaCEP foi substituído pelo dublê tests/mock_viacep.py (mesmo formato de resposta), configurado via VIACEP_URL. Com internet, a API consome https://viacep.com.br diretamente.

### 7. Cadastro de animal e vínculo de microchip

*Esperado:* 201; vínculo registra veterinário e data; animal sincronizado  
*Resultado:* **APROVADO** (14 ms)

- [OK] POST /api/animais -> HTTP 201, id=3
- [OK] POST /api/animais/3/microchip (076076888915062) -> HTTP 201
- [OK] vínculo por Dra. Ana Souza (CRMV 12345-RJ) em 2026-11-25 04:01:54
- [OK] situação governamental do animal: SINCRONIZADO (protocolo GOV-20261125-4260D370)

### 8. Rejeição de microchip já utilizado

*Esperado:* HTTP 409  
*Resultado:* **APROVADO** (7 ms)

- [OK] vincular 076076888915062 a outro animal -> HTTP 409: Microchip já utilizado (animal #3 - Rex (teste)). Um microchip não pode ser reutilizado.

### 9. Registro de consulta e consulta ao histórico clínico

*Esperado:* 201; consulta aparece no histórico do animal  
*Resultado:* **APROVADO** (8 ms)

- [OK] POST /api/consultas -> HTTP 201, id=1, veterinário=Dra. Ana Souza
- [OK] GET /api/animais/3/consultas -> 1 registro(s) no histórico
- [OK] peso atual do animal atualizado para 23.1 kg

### 10. Registro de vacina e consulta às próximas doses

*Esperado:* 201; próxima dose listada  
*Resultado:* **APROVADO** (9 ms)

- [OK] POST /api/vacinas (V10) -> HTTP 201, id=1
- [OK] GET /api/animais/3/vacinas -> próximas doses: [('V10 Polivalente', '2026-12-16')]
- [OK] GET /api/vacinas/proximas-doses?dias=30 -> 1 dose(s) prevista(s) na clínica

### 11. Cadastro e atualização de animal na API governamental simulada

*Esperado:* Animal encontrado no serviço externo; atualização confirmada  
*Resultado:* **APROVADO** (16 ms)

- [OK] cadastro: GET situacao-governo -> registro externo ENCONTRADO (nome=Rex (teste), cor=Preto)
- [OK] PUT /api/animais/3 -> integração ATUALIZACAO_ANIMAL CONFIRMADA protocolo GOV-20261125-605F35BC
- [OK] GET http://127.0.0.1:5001/api/governo/animais/076076888915062 -> cor='Preto e branco'

### 12. Envio obrigatório de vacina antirrábica

*Esperado:* Registro local + comunicação CONFIRMADA com protocolo, inclusive para animal ainda não cadastrado no serviço externo  
*Resultado:* **APROVADO** (35 ms)

- [OK] POST /api/vacinas (ANTIRRABICA) -> HTTP 201, registro local REGISTRADA
- [OK] comunicação obrigatória: CONFIRMADA - protocolo GOV-20261125-49ACC676
- [OK] serviço externo possui 1 vacinação(ões) antirrábica(s) para 076076888915062
- [OK] animal Luna com microchip 076125793840148 criado com o serviço externo fora do ar -> cadastro externo PENDENTE
- [OK] antirrábica de animal não cadastrado no serviço externo -> CONFIRMADA (protocolo GOV-20261125-59BF053B, cadastro_implicito_animal=True)

### 13. Ausência de comunicação obrigatória para vacina não antirrábica

*Esperado:* Nenhuma integração gerada  
*Resultado:* **APROVADO** (8 ms)

- [OK] vacina V10 (POLIVALENTE_CANINA): comunicação=NAO_SE_APLICA, integração=None
- [OK] texto digitado contendo 'raiva' com tipo GRIPE_CANINA -> não classificada como antirrábica (classificação estruturada pelo tipo)
- [OK] serviço externo continua com 1 vacinação(ões) para 076076888915062

### 14. Indisponibilidade da API governamental e registro de pendência

*Esperado:* Vacina registrada localmente; comunicação PENDENTE com erro e tentativa contabilizada  
*Resultado:* **APROVADO** (16 ms)

- [OK] POST /api/vacinas com o serviço fora do ar -> HTTP 201; vacina #5 registrada localmente (APLICADA)
- [OK] comunicação PENDENTE, tentativas=1, erro='Serviço governamental temporariamente indisponível (simulação).'
- [OK] integração #6: próxima tentativa automática agendada para 2026-11-25 04:02:25, chave VAC-ANTIRRABICA-5
- [OK] GET /api/integracoes?situacao=PENDENTE -> 2 pendência(s)
- [OK] serviço externo responde HTTP 503 (indisponível)

### 15. Reenvio de comunicação pendente e confirmação posterior

*Esperado:* Após o retorno do serviço, reenvio confirma com protocolo  
*Resultado:* **APROVADO** (23 ms)

- [OK] POST /api/integracoes/6/reenviar -> CONFIRMADA, protocolo GOV-20261125-D74F02B5, tentativas=2
- [OK] POST /api/integracoes/reprocessar-pendentes -> processadas=1, confirmadas=1, pendentes=0
- [OK] cadastro pendente da Luna regularizado -> SINCRONIZADO
- [OK] serviço externo agora tem 2 vacinações antirrábicas para 076076888915062 (a de 12 + a regularizada)

### 16. Repetição de solicitação sem duplicidade de vacinação no serviço externo

*Esperado:* Mesmo protocolo; contagem inalterada  
*Resultado:* **APROVADO** (15 ms)

- [OK] reenvio forçado pela clínica -> protocolo GOV-20261125-D74F02B5 (igual ao original); msg: Solicitação repetida: o serviço externo devolveu o MESMO protocolo, sem novo registro.
- [OK] POST direto com a mesma Idempotency-Key (VAC-ANTIRRABICA-5) -> HTTP 201, Idempotent-Replay=true
- [OK] mesma aplicação com OUTRA chave -> HTTP 200, duplicidade_evitada=True
- [OK] contagem no serviço externo após 3 repetições: 2 (antes: 2)

### C1. Proteção de endpoints sem autenticação

*Esperado:* HTTP 401  
*Resultado:* **APROVADO** (1 ms)

- [OK] GET /api/tutores sem token -> HTTP 401

### C2. Raça incompatível com a espécie

*Esperado:* HTTP 422  
*Resultado:* **APROVADO** (1 ms)

- [OK] gato com raça Labrador -> HTTP 422: A raça selecionada não é compatível com a espécie informada.

### C3. Substituição de microchip preservando histórico

*Esperado:* Novo chip ativo, anterior inativo com motivo  
*Resultado:* **APROVADO** (14 ms)

- [OK] substituir sem motivo -> HTTP 422
- [OK] histórico: [('076827908774430', 'ativo'), ('076076888915062', 'inativo')]
- [OK] serviço externo marcou o chip antigo como SUBSTITUIDO

### C4. Cadastro de veterinário com confirmação de senha por código

*Esperado:* 403 antes; 200 após confirmar  
*Resultado:* **APROVADO** (478 ms)

- [OK] POST /api/auth/registro -> HTTP 201 (código simulado 723273)
- [OK] login antes de confirmar -> HTTP 403
- [OK] código errado -> HTTP 400
- [OK] código correto -> HTTP 200
- [OK] login após confirmar -> HTTP 200

### C5. Logout encerra a sessão

*Esperado:* token deixa de valer (401)  
*Resultado:* **APROVADO** (87 ms)

- [OK] POST /api/auth/logout -> HTTP 200
- [OK] GET /api/auth/me com token encerrado -> HTTP 401

### C6. Antirrábica em animal sem microchip: registro local mantido e envio após o vínculo

*Esperado:* FALHA aguardando microchip -> CONFIRMADA após vincular  
*Resultado:* **APROVADO** (21 ms)

- [OK] vacina registrada (APLICADA); comunicação FALHA: Animal sem microchip vinculado: não é possível comunicar ao serviço externo.
- [OK] após vincular o microchip a comunicação foi reenviada -> CONFIRMADA (protocolo GOV-20261125-3DC906F5)

### C7. Timeout com processamento tardio no serviço externo: reenvio reconhecido sem duplicar

*Esperado:* PENDENTE por timeout -> reenvio CONFIRMADA (replay idempotente); 1 único registro externo  
*Resultado:* **APROVADO** (9054 ms)

- [OK] clínica desistiu após o timeout de leitura: PENDENTE — Timeout ao comunicar com a API governamental.
- [OK] reenvio -> CONFIRMADA: Reenvio reconhecido pelo serviço externo (idempotente, sem duplicidade).
- [OK] registros externos antes/depois do reenvio: 2/2 (sem duplicidade)
