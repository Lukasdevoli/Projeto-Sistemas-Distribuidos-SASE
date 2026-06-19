import os
from datetime import datetime

_IMG = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'image.png'))


def _intervalo(h, anterior):
    if not anterior:
        return "Primeiro atendimento"
    s = int((h["hora"] - anterior["hora"]).total_seconds())
    if s < 60:
        return "{}s apos {}".format(s, anterior["senha"])
    m, r = divmod(s, 60)
    return "{}min {}s apos {}".format(m, r, anterior["senha"])


def _safe(txt, maxlen=120):
    try:
        return str(txt)[:maxlen].encode("latin-1", errors="replace").decode("latin-1")
    except Exception:
        return str(txt)[:maxlen]


def _stats_sessao(historico):
    """Calcula estatísticas de sessão a partir do histórico."""
    if not historico:
        return {}

    inicio  = historico[0]["hora"]
    fim     = historico[-1]["hora"]
    dur_s   = int((fim - inicio).total_seconds())

    if dur_s < 60:
        dur_str = "{}s".format(dur_s)
    else:
        m, s = divmod(dur_s, 60)
        dur_str = "{}min {}s".format(m, s)

    intervalos = []
    for i in range(1, len(historico)):
        dt = int((historico[i]["hora"] - historico[i - 1]["hora"]).total_seconds())
        intervalos.append((dt, historico[i]["senha"]))

    stats = {
        "Inicio da sessao":     inicio.strftime("%H:%M:%S"),
        "Fim da ultima chamada": fim.strftime("%H:%M:%S"),
        "Duracao total":        dur_str,
    }

    if intervalos:
        media   = sum(d for d, _ in intervalos) / len(intervalos)
        rapido  = min(intervalos, key=lambda x: x[0])
        lento   = max(intervalos, key=lambda x: x[0])
        stats["Tempo medio entre chamadas"] = "{:.0f}s".format(media)
        stats["Chamada mais rapida"]        = "{}s  ({})".format(rapido[0], rapido[1])
        stats["Chamada mais lenta"]         = "{}s  ({})".format(lento[0], lento[1])

    if dur_s > 0:
        stats["Ritmo estimado"] = "{:.0f} atendimentos/hora".format(
            len(historico) / (dur_s / 3600))

    return stats


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------

def gerar_txt(titulo, historico, com_guiche=True, extras=None):
    sep = "=" * 62
    linhas = [sep, "   {}".format(titulo),
              "   Gerado em: {}".format(datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
              sep, ""]

    if not historico:
        linhas.append("   Nenhum atendimento registrado.")
    else:
        if com_guiche:
            linhas.append("  {:<4} {:<8} {:<24} {:<14} {:<8} {:<10} INTERVALO".format(
                "#", "SENHA", "NOME", "TIPO", "GUICHE", "HORARIO"))
        else:
            linhas.append("  {:<4} {:<8} {:<24} {:<14} {:<10} INTERVALO".format(
                "#", "SENHA", "NOME", "TIPO", "HORARIO"))
        linhas.append("  " + "-" * 72)

        anterior = None
        for h in historico:
            iv = _intervalo(h, anterior)
            nome_val = h.get("nome", "")
            if com_guiche:
                linhas.append("  {:<4} {:<8} {:<24} {:<14} {:<8} {:<10} {}".format(
                    h["ordem"], h["senha"], nome_val[:23], h["tipo"],
                    "G{}".format(h["guiche"]), h["hora"].strftime("%H:%M:%S"), iv))
            else:
                linhas.append("  {:<4} {:<8} {:<24} {:<14} {:<10} {}".format(
                    h["ordem"], h["senha"], nome_val[:23], h["tipo"],
                    h["hora"].strftime("%H:%M:%S"), iv))
            anterior = h

        total   = len(historico)
        normais = sum(1 for h in historico if h["tipo"] == "Normal")
        prios   = total - normais
        linhas += [
            "",
            "  " + "-" * 56,
            "  Resumo:",
            "  Total de atendimentos : {}".format(total),
            "  Normal                : {}".format(normais),
            "  Prioritario           : {}".format(prios),
        ]

    # Extras (fila restante, stats, etc.)
    if extras:
        linhas += ["", "  " + "-" * 56, "  Informacoes Adicionais:"]
        for k, v in extras.items():
            linhas.append("  {:<32} {}".format(k + ":", v))

    linhas += ["", sep]
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _pdf_secao(pdf, titulo):
    """Imprime um cabeçalho de seção azul."""
    pdf.set_fill_color(15, 52, 96)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 8, titulo, ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)


def _pdf_kv(pdf, chave, valor, largura_chave=70):
    """Imprime uma linha chave: valor."""
    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(largura_chave, 6, "{}:".format(chave))
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, _safe(str(valor)), ln=True)


def gerar_pdf(caminho, titulo, historico, log_texto=None, com_guiche=True, extras=None):
    """Gera PDF. Retorna (True, '') ou (False, mensagem_de_erro)."""
    try:
        from fpdf import FPDF
    except ImportError:
        return False, "fpdf2 nao instalado. Execute: pip install fpdf2"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ---- Cabeçalho ----
    tem_logo = os.path.isfile(_IMG)
    logo_w, logo_h, logo_x, logo_y = 56, 24, 8, 6
    titulo_x = logo_x + logo_w + 6 if tem_logo else 10
    header_h = 36

    if tem_logo:
        try:
            pdf.image(_IMG, x=logo_x, y=logo_y, w=logo_w, h=logo_h)
        except Exception:
            titulo_x = 10

    pdf.set_xy(titulo_x, logo_y + 2)
    pdf.set_text_color(26, 26, 46)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "SASE - Sistema de Atendimento por Senha Eletronica", ln=True)
    pdf.set_x(titulo_x)
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 5, _safe(titulo), ln=True)
    pdf.set_x(titulo_x)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 5, "Gerado em: {}   |   IF Crato - Sistemas Distribuidos".format(
        datetime.now().strftime("%d/%m/%Y  %H:%M:%S")), ln=True)

    pdf.set_draw_color(26, 26, 46)
    pdf.set_line_width(0.7)
    pdf.line(8, header_h, 202, header_h)
    pdf.set_xy(10, header_h + 5)

    # ---- Tabela de atendimentos ----
    pdf.set_text_color(0, 0, 0)
    _pdf_secao(pdf, "Historico de Atendimentos")
    pdf.ln(1)

    if not historico:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 8, "Nenhum atendimento registrado.", ln=True)
    else:
        if com_guiche:
            cols   = ["#", "Senha", "Nome", "Tipo", "Guiche", "Horario", "Intervalo"]
            widths = [10, 18, 46, 28, 24, 22, 42]
        else:
            cols   = ["#", "Senha", "Nome", "Tipo", "Horario", "Intervalo"]
            widths = [10, 18, 50, 28, 22, 62]

        # Cabeçalho da tabela
        pdf.set_fill_color(15, 52, 96)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 9)
        for col, w in zip(cols, widths):
            pdf.cell(w, 8, col, border=1, fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", size=9)
        anterior, alt = None, False
        for h in historico:
            iv = _intervalo(h, anterior)
            nome_val = _safe(h.get("nome", ""))
            pdf.set_fill_color(245, 247, 255) if alt else pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(0, 0, 0)
            if com_guiche:
                vals = [str(h["ordem"]), h["senha"], nome_val, h["tipo"],
                        "Guiche {}".format(h["guiche"]),
                        h["hora"].strftime("%H:%M:%S"), iv]
            else:
                vals = [str(h["ordem"]), h["senha"], nome_val, h["tipo"],
                        h["hora"].strftime("%H:%M:%S"), iv]
            for val, w in zip(vals, widths):
                pdf.cell(w, 7, _safe(val), border=1, fill=True)
            pdf.ln()
            anterior = h
            alt = not alt

        # ---- Resumo ----
        pdf.ln(5)
        total   = len(historico)
        normais = sum(1 for h in historico if h["tipo"] == "Normal")
        prios   = total - normais
        _pdf_secao(pdf, "Resumo")
        for label, val in [("Total de atendimentos", total),
                            ("Normal",               normais),
                            ("Prioritario",          prios)]:
            _pdf_kv(pdf, label, val)

    # ---- Informações adicionais (fila restante, stats, etc.) ----
    if extras:
        pdf.ln(4)
        _pdf_secao(pdf, "Informacoes Adicionais")
        for k, v in extras.items():
            _pdf_kv(pdf, k, v)

    # ---- Log do servidor (página separada) ----
    if log_texto and log_texto.strip():
        pdf.add_page()
        if tem_logo:
            try:
                pdf.image(_IMG, x=logo_x, y=logo_y, w=logo_w, h=logo_h)
            except Exception:
                pass
        pdf.set_xy(titulo_x, logo_y + 4)
        pdf.set_text_color(26, 26, 46)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Log do Servidor", ln=True)
        pdf.set_draw_color(26, 26, 46)
        pdf.set_line_width(0.7)
        pdf.line(8, header_h, 202, header_h)
        pdf.set_xy(10, header_h + 5)
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Courier", size=8)
        for linha in log_texto.splitlines():
            linha = linha.strip()
            if not linha:
                continue
            try:
                pdf.cell(0, 5, _safe(linha), ln=True)
            except Exception:
                pass

    try:
        pdf.output(caminho)
        return True, ""
    except Exception as e:
        return False, str(e)
