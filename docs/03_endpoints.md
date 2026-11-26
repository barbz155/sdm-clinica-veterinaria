# 3. Documentação dos Endpoints

A especificação completa (OpenAPI 3) está em:

- **API da clínica:** `api_clinica/openapi.yaml`, navegável em <http://127.0.0.1:5000/docs>
- **API governamental:** `api_governo/openapi.yaml`, navegável em <http://127.0.0.1:5001/docs>

> O Swagger UI é carregado de CDN. Sem internet, abra os arquivos `.yaml` em <https://editor.swagger.io>.

**Padrão de erro (clínica):** `{"erro": "mensagem", "status": 422, "detalhes": ["campo X é obrigatório."]}`
**Autenticação (clínica):** `Authorization: Bearer <token>`, obtido em `POST /api/auth/login`.
**Autenticação (governo):** `X-Api-Key: chave-clinica-sdm-123`. Escritas exigem `Idempotency-Key`.

## 3.1 API privada da clínica (porta 5000)

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| POST | `/api/auth/login` | Login (ativo + senha confirmada) | — |
| POST | `/api/auth/logout` | Encerra a sessão | Sim |
| GET | `/api/auth/me` | Veterinário autenticado | Sim |
| POST | `/api/auth/registro` | Cadastro de veterinário (gera o código de confirmação) | — |
| POST | `/api/auth/confirmar-senha` | Confirma a senha com o código | — |
| POST | `/api/auth/reenviar-codigo` | Reenvia o código | — |
| GET | `/api/dev/emails` | E-mails simulados (DEV_MODE) | — |
| GET | `/api/cep/{cep}` | Consulta o ViaCEP | Sim |
| POST · GET · PUT | `/api/enderecos`, `/api/enderecos/{id}` | Endereços | Sim |
| GET | `/api/clinica/endereco` | Endereço da clínica | Sim |
| GET · POST | `/api/tutores` | Lista (q, situacao) / cadastra | Sim |
| GET · PUT · DELETE | `/api/tutores/{id}` | Consulta / altera / inativa | Sim |
| GET | `/api/tutores/{id}/animais` | Animais do tutor | Sim |
| GET · POST | `/api/especies` | Espécies | Sim |
| GET · PUT · DELETE | `/api/especies/{id}` | Espécie | Sim |
| GET | `/api/especies/{id}/racas` | Raças da espécie | Sim |
| GET · POST | `/api/racas` | Raças | Sim |
| PUT · DELETE | `/api/racas/{id}` | Raça | Sim |
| GET | `/api/veterinarios`, `/api/veterinarios/{id}` | Veterinários | Sim |
| PUT | `/api/veterinarios/{id}` | Altera dados | Sim |
| PATCH | `/api/veterinarios/{id}/situacao` | Ativa / inativa | Sim |
| GET · POST | `/api/animais` | Lista (q, tutor_id, microchip, gov_situacao) / cadastra | Sim |
| GET · PUT · DELETE | `/api/animais/{id}` | Consulta / atualiza / inativa | Sim |
| POST | `/api/animais/{id}/microchip` | Vincula ou substitui o microchip | Sim |
| GET | `/api/animais/{id}/microchips` | Histórico de vínculos | Sim |
| GET | `/api/animais/{id}/consultas` | Histórico clínico | Sim |
| GET | `/api/animais/{id}/vacinas` | Histórico de vacinas + próximas doses | Sim |
| POST | `/api/animais/{id}/sincronizar-governo` | Envia cadastro/atualização ao governo | Sim |
| GET | `/api/animais/{id}/situacao-governo` | Situação local + registro externo | Sim |
| GET | `/api/animais/{id}/integracoes` | Integrações do animal | Sim |
| GET · POST | `/api/consultas` | Lista (data, situacao) / registra | Sim |
| GET · PUT · DELETE | `/api/consultas/{id}` | Consulta / altera / cancela | Sim |
| GET | `/api/vacinas/tipos` | Classificação estruturada | Sim |
| POST | `/api/vacinas` | Registra a aplicação (dispara a comunicação se antirrábica) | Sim |
| GET · PUT · DELETE | `/api/vacinas/{id}` | Consulta / altera agendada / cancela agendada | Sim |
| GET | `/api/vacinas/proximas-doses?dias=30` | Próximas doses da clínica | Sim |
| GET | `/api/integracoes` | Lista (situacao, tipo, animal_id) | Sim |
| GET | `/api/integracoes/resumo` | Contagem por situação | Sim |
| GET | `/api/integracoes/{id}` | Detalhe (payload, resposta, chave) | Sim |
| POST | `/api/integracoes/{id}/reenviar[?forcar=true]` | Reenvio manual | Sim |
| POST | `/api/integracoes/reprocessar-pendentes` | Reprocessa todas as pendências | Sim |
| GET | `/api/health` | Saúde + status do governo | — |

### Exemplo — registrar vacina antirrábica

```http
POST /api/vacinas
Authorization: Bearer eyJ...
Content-Type: application/json

{ "animal_id": 3, "nome_vacina": "Rabisin", "tipo_vacina": "ANTIRRABICA",
  "fabricante": "Laboratório Fictício", "lote": "RAB-2026-07", "data_aplicacao": "2026-11-26",
  "dose": "Reforço anual", "via_aplicacao": "SUBCUTANEA", "data_proxima_dose": "2027-11-26",
  "data_validade_lote": "2027-06-30" }
```

```json
201 Created
{ "id": 7, "situacao": "APLICADA", "antirrabica": true,
  "comunicacao_governo": { "obrigatoria": true, "registro_local": "REGISTRADA",
    "situacao": "CONFIRMADA", "protocolo": "GOV-20261126-41AF314E", "tentativas": 1, "integracao_id": 5 } }
```

Com o serviço governamental fora do ar, a mesma chamada retorna `201` com `"situacao": "PENDENTE"` e `"mensagem": "Serviço governamental temporariamente indisponível"`.

## 3.2 API governamental simulada (porta 5001)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/governo/health` | Disponibilidade |
| POST | `/api/governo/animais` | Cadastra animal (201; 200 se for o mesmo sistema de origem; 409 se o microchip for de outra origem) |
| GET | `/api/governo/animais/{microchip}` | Consulta animal + vacinações |
| PUT | `/api/governo/animais/{microchip}` | Atualiza dados cadastrais |
| POST | `/api/governo/vacinacoes-antirrabicas` | Recebe vacinação (com cadastro implícito, se necessário) |
| GET | `/api/governo/vacinacoes-antirrabicas?microchip=` | Lista vacinações recebidas |
| GET | `/api/governo/operacoes/{protocolo}` | Resultado de uma operação |
| GET · PUT | `/api/governo/admin/simulacao` | Modo: NORMAL, INDISPONIVEL (503), LENTO (atraso → timeout), ERRO_INTERMITENTE (50% 503) |
| GET | `/api/governo/admin/estatisticas` | Indicadores |
| GET | `/` | Painel web do serviço (alternar a simulação, ver registros e protocolos) |

### Exemplo de idempotência

```http
POST /api/governo/vacinacoes-antirrabicas
X-Api-Key: chave-clinica-sdm-123
Idempotency-Key: VAC-ANTIRRABICA-5
```
1ª chamada → `201` com o protocolo `GOV-…-D53959B5`.
2ª chamada com a mesma chave → `201` com o **mesmo protocolo** e o cabeçalho `Idempotent-Replay: true` (nada é gravado).
Mesma aplicação com outra chave → `200` com `"duplicidade_evitada": true` (nada é gravado).
