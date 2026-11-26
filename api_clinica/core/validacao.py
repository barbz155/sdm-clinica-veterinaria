"""Validações reutilizáveis e exceção de regra de negócio."""
import re
from datetime import date, datetime


class ErroNegocio(Exception):
    """Erro de validação/regra de negócio, convertido em resposta HTTP padronizada."""

    def __init__(self, mensagem, status=422, erros=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.erros = erros or []


class Validador:
    """Acumula erros de validação de um payload e lança ErroNegocio ao final."""

    def __init__(self, dados):
        self.d = dados or {}
        self.erros = []

    # ---- utilitários ----
    def _v(self, campo):
        v = self.d.get(campo)
        return v.strip() if isinstance(v, str) else v

    def obrigatorio(self, campo, rotulo=None, max_len=None):
        v = self._v(campo)
        if v is None or v == "":
            self.erros.append(f"{rotulo or campo} é obrigatório.")
            return None
        if max_len and isinstance(v, str) and len(v) > max_len:
            self.erros.append(f"{rotulo or campo} deve ter no máximo {max_len} caracteres.")
        return v

    def opcional(self, campo, max_len=None):
        v = self._v(campo)
        if v in ("", None):
            return None
        if max_len and isinstance(v, str) and len(v) > max_len:
            self.erros.append(f"{campo} deve ter no máximo {max_len} caracteres.")
        return v

    def cpf(self, campo="cpf"):
        v = somente_digitos(self._v(campo))
        if not v:
            self.erros.append("CPF é obrigatório.")
        elif not cpf_valido(v):
            self.erros.append("CPF inválido.")
        return v

    def email(self, campo="email"):
        v = (self._v(campo) or "").lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            self.erros.append("E-mail inválido.")
        return v

    def telefone(self, campo="telefone"):
        v = somente_digitos(self._v(campo))
        if not (10 <= len(v) <= 11):
            self.erros.append("Telefone deve ter DDD + número (10 ou 11 dígitos).")
        return v

    def data(self, campo, rotulo=None, obrigatoria=True, nao_futura=False):
        v = self._v(campo)
        if not v:
            if obrigatoria:
                self.erros.append(f"{rotulo or campo} é obrigatória.")
            return None
        try:
            d = date.fromisoformat(str(v)[:10])
        except ValueError:
            self.erros.append(f"{rotulo or campo} deve estar no formato AAAA-MM-DD.")
            return None
        if nao_futura and d > date.today():
            self.erros.append(f"{rotulo or campo} não pode ser futura.")
        return d.isoformat()

    def data_hora(self, campo, rotulo=None):
        v = self._v(campo)
        if not v:
            self.erros.append(f"{rotulo or campo} é obrigatória.")
            return None
        try:
            return datetime.fromisoformat(str(v)).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            self.erros.append(f"{rotulo or campo} deve estar no formato AAAA-MM-DDTHH:MM.")
            return None

    def numero(self, campo, rotulo=None, obrigatorio=True, minimo=None, maximo=None, inteiro=False):
        v = self._v(campo)
        if v in (None, ""):
            if obrigatorio:
                self.erros.append(f"{rotulo or campo} é obrigatório.")
            return None
        try:
            n = int(v) if inteiro else float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            self.erros.append(f"{rotulo or campo} deve ser numérico.")
            return None
        if minimo is not None and n < minimo:
            self.erros.append(f"{rotulo or campo} deve ser maior ou igual a {minimo}.")
        if maximo is not None and n > maximo:
            self.erros.append(f"{rotulo or campo} deve ser menor ou igual a {maximo}.")
        return n

    def escolha(self, campo, opcoes, rotulo=None, obrigatorio=True, padrao=None):
        v = self._v(campo)
        if v in (None, ""):
            if obrigatorio and padrao is None:
                self.erros.append(f"{rotulo or campo} é obrigatório.")
            return padrao
        v = str(v).upper()
        if v not in opcoes:
            self.erros.append(f"{rotulo or campo} deve ser um de: {', '.join(opcoes)}.")
        return v

    def adicionar(self, mensagem):
        self.erros.append(mensagem)

    def verificar(self):
        if self.erros:
            raise ErroNegocio("Dados inválidos.", 422, self.erros)


def somente_digitos(v):
    return re.sub(r"\D", "", str(v or ""))


def cpf_valido(cpf):
    cpf = somente_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(cpf[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11
        if dv == 10:
            dv = 0
        if dv != int(cpf[n]):
            return False
    return True


def senha_forte(senha):
    return (isinstance(senha, str) and len(senha) >= 8 and re.search(r"[A-Za-z]", senha)
            and re.search(r"\d", senha))


def microchip_valido(codigo):
    return bool(re.fullmatch(r"\d{15}", str(codigo or "")))


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
