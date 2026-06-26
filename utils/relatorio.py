"""
relatorio.py — Geração de relatórios de atendimento do SASE (TXT e PDF).

O QUE FAZ:
    A partir do histórico de senhas atendidas (uma lista de dicionários, cada um
    com ordem, senha, nome, tipo, guichê e horário), produz dois formatos de
    relatório:
        - TXT  : texto puro tabulado, leve, fácil de abrir em qualquer lugar.
        - PDF  : documento formatado com logo do IF, tabela colorida, resumo,
                 estatísticas e, opcionalmente, o log do servidor.

COMO USA:
    txt = gerar_txt("Relatorio do Guiche 1", historico)
    ok, msg = gerar_pdf("/caminho/saida.pdf", "Relatorio Geral", historico)

ONDE SE ENCAIXA NO SISTEMA:
    É a camada de SAÍDA/persistência de resultados. O histórico chega pronto de
    quem consumiu o protocolo de senhas (servidor/guichê via sockets TCP — ver
    utils/conexao.py); este módulo apenas formata, não fala com a rede.

DEPENDÊNCIA OPCIONAL:
    O PDF usa a biblioteca fpdf2. Se ela não estiver instalada, gerar_pdf
    retorna um erro tratado (não quebra o programa); gerar_txt nunca depende de
    nada externo.

Disciplina: Sistemas Distribuídos — IFCE Campus Crato
"""

import os
from datetime import datetime

# Caminho absoluto da logo do IF usada no cabeçalho do PDF.
# os.path.normpath é aplicado porque montamos o caminho subindo um nível
# (".." a partir de utils/), o que gera trechos como "utils/../image.png".
# normpath resolve isso para um caminho limpo e, principalmente, no separador
# CORRETO de cada SO (\ no Windows, / no Linux) — evita que o FPDF falhe ao
# abrir a imagem por causa de barras misturadas.
_IMG = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'image.png'))


def _intervalo(h, anterior):
    """Descreve o tempo decorrido entre um atendimento e o anterior.

    Serve para mostrar o ritmo da fila linha a linha no relatório.

    Args:
        h (dict): atendimento atual; usa a chave "hora" (datetime).
        anterior (dict | None): atendimento imediatamente anterior, ou None se
            este for o primeiro da sessão.

    Returns:
        str: texto humanizado como "12s apos N5" ou "1min 4s apos N4";
            "Primeiro atendimento" quando não há anterior.
    """
    if not anterior:
        return "Primeiro atendimento"
    s = int((h["hora"] - anterior["hora"]).total_seconds())
    # Abaixo de 1 minuto mostramos só segundos; acima, minutos + segundos.
    if s < 60:
        return "{}s apos {}".format(s, anterior["senha"])
    m, r = divmod(s, 60)
    return "{}min {}s apos {}".format(m, r, anterior["senha"])


def _safe(txt, maxlen=120):
    """Sanitiza um texto para ser escrito no PDF sem quebrar a fonte.

    POR QUE latin-1: as fontes padrão (core fonts) do FPDF/fpdf2 trabalham com
    a codificação latin-1, NÃO suportando UTF-8 diretamente. Caracteres fora do
    latin-1 (alguns acentos/emojis) lançariam exceção na escrita. Fazemos
    encode para latin-1 substituindo o que não couber e decode de volta,
    garantindo uma string sempre "imprimível". Também trunca em maxlen para não
    estourar a largura das células da tabela.

    Args:
        txt: valor de qualquer tipo (convertido para str).
        maxlen (int): tamanho máximo permitido.

    Returns:
        str: texto seguro para o FPDF, truncado em maxlen.
    """
    try:
        return str(txt)[:maxlen].encode("latin-1", errors="replace").decode("latin-1")
    except Exception:
        return str(txt)[:maxlen]


def _stats_sessao(historico):
    """Calcula estatísticas agregadas da sessão de atendimento.

    Métricas produzidas: início/fim da sessão, duração total, tempo médio entre
    chamadas, chamada mais rápida e mais lenta, e o ritmo estimado em
    atendimentos por hora. Úteis para avaliar o desempenho do guichê.

    Args:
        historico (list[dict]): atendimentos em ordem cronológica; cada item
            precisa de "hora" (datetime) e "senha".

    Returns:
        dict: pares rótulo->valor já formatados como string. Dicionário vazio
            se o histórico estiver vazio.
    """
    if not historico:
        return {}

    inicio  = historico[0]["hora"]
    fim     = historico[-1]["hora"]
    dur_s   = int((fim - inicio).total_seconds())

    # Formata a duração total de forma legível (só segundos vs minutos+segundos).
    if dur_s < 60:
        dur_str = "{}s".format(dur_s)
    else:
        m, s = divmod(dur_s, 60)
        dur_str = "{}min {}s".format(m, s)

    # Coleta o intervalo (em segundos) entre cada par consecutivo de chamadas,
    # guardando junto a senha de destino para depois identificar a mais
    # rápida/lenta.
    intervalos = []
    for i in range(1, len(historico)):
        dt = int((historico[i]["hora"] - historico[i - 1]["hora"]).total_seconds())
        intervalos.append((dt, historico[i]["senha"]))

    stats = {
        "Inicio da sessao":     inicio.strftime("%H:%M:%S"),
        "Fim da ultima chamada": fim.strftime("%H:%M:%S"),
        "Duracao total":        dur_str,
    }

    # Métricas de intervalo só fazem sentido com 2+ atendimentos.
    if intervalos:
        media   = sum(d for d, _ in intervalos) / len(intervalos)
        rapido  = min(intervalos, key=lambda x: x[0])
        lento   = max(intervalos, key=lambda x: x[0])
        stats["Tempo medio entre chamadas"] = "{:.0f}s".format(media)
        stats["Chamada mais rapida"]        = "{}s  ({})".format(rapido[0], rapido[1])
        stats["Chamada mais lenta"]         = "{}s  ({})".format(lento[0], lento[1])

    # Evita divisão por zero quando todos os atendimentos têm o mesmo horário.
    if dur_s > 0:
        stats["Ritmo estimado"] = "{:.0f} atendimentos/hora".format(
            len(historico) / (dur_s / 3600))

    return stats


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------

def gerar_txt(titulo, historico, com_guiche=True, extras=None):
    """Gera o relatório em texto puro (string).

    Args:
        titulo (str): título exibido no topo do relatório.
        historico (list[dict]): atendimentos em ordem cronológica.
        com_guiche (bool): se True, inclui a coluna "GUICHE" na tabela. Útil
            para relatórios GERAIS (vários guichês); em relatórios de um único
            guichê a coluna é redundante e pode ser omitida (False).
        extras (dict | None): informações adicionais (ex.: fila restante,
            estatísticas de ``_stats_sessao``) impressas numa seção própria ao
            final, como pares "rótulo: valor".

    Returns:
        str: o relatório completo pronto para salvar ou exibir.
    """
    sep = "=" * 62
    linhas = [sep, "   {}".format(titulo),
              "   Gerado em: {}".format(datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
              sep, ""]

    if not historico:
        linhas.append("   Nenhum atendimento registrado.")
    else:
        # Cabeçalho da tabela varia conforme exiba ou não a coluna de guichê.
        if com_guiche:
            linhas.append("  {:<4} {:<8} {:<24} {:<14} {:<8} {:<10} INTERVALO".format(
                "#", "SENHA", "NOME", "TIPO", "GUICHE", "HORARIO"))
        else:
            linhas.append("  {:<4} {:<8} {:<24} {:<14} {:<10} INTERVALO".format(
                "#", "SENHA", "NOME", "TIPO", "HORARIO"))
        linhas.append("  " + "-" * 72)

        # Percorre o histórico mantendo o item anterior para calcular o intervalo.
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

        # Resumo: contagem total e separação entre Normal e Prioritário.
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
    """Imprime um cabeçalho de seção (faixa azul com texto branco).

    Helper de formatação para dar consistência visual às seções do PDF.

    Args:
        pdf: instância FPDF ativa.
        titulo (str): texto do cabeçalho.
    """
    pdf.set_fill_color(15, 52, 96)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 8, titulo, ln=True, fill=True)
    # Restaura a cor do texto para preto para o conteúdo que vem depois.
    pdf.set_text_color(0, 0, 0)


def _pdf_kv(pdf, chave, valor, largura_chave=70):
    """Imprime uma linha no formato "chave: valor" no PDF.

    Helper de formatação usado nas seções de resumo e informações adicionais,
    com a chave em cinza e o valor em negrito preto.

    Args:
        pdf: instância FPDF ativa.
        chave (str): rótulo do campo.
        valor: valor do campo (sanitizado por ``_safe``).
        largura_chave (int): largura reservada para a coluna da chave (mm).
    """
    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(largura_chave, 6, "{}:".format(chave))
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, _safe(str(valor)), ln=True)


def gerar_pdf(caminho, titulo, historico, log_texto=None, com_guiche=True, extras=None):
    """Gera o relatório em PDF e o salva em disco.

    Estrutura: cabeçalho com logo do IF, tabela de atendimentos (zebrada),
    resumo, informações adicionais e — se fornecido — o log do servidor em uma
    página própria.

    Args:
        caminho (str): caminho de saída do arquivo PDF.
        titulo (str): subtítulo do relatório (abaixo do nome do sistema).
        historico (list[dict]): atendimentos em ordem cronológica.
        log_texto (str | None): log bruto do servidor; se presente e não vazio,
            é anexado em uma página separada (fonte monoespaçada).
        com_guiche (bool): inclui a coluna "Guiche" na tabela (ver gerar_txt).
        extras (dict | None): informações adicionais (fila restante, stats).

    Returns:
        tuple[bool, str]: (True, "") em caso de sucesso; (False, mensagem) em
            caso de erro — por exemplo, fpdf2 ausente ou falha ao escrever.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        # Falha controlada: o chamador decide como avisar o usuário.
        return False, "fpdf2 nao instalado. Execute: pip install fpdf2"

    pdf = FPDF()
    # Quebra de página automática deixando 15mm de margem inferior.
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ---- Cabeçalho ----
    tem_logo = os.path.isfile(_IMG)
    logo_w, logo_h, logo_x, logo_y = 56, 24, 8, 6
    # Se houver logo, o título começa à direita dela; senão, na margem esquerda.
    titulo_x = logo_x + logo_w + 6 if tem_logo else 10
    header_h = 36

    if tem_logo:
        try:
            pdf.image(_IMG, x=logo_x, y=logo_y, w=logo_w, h=logo_h)
        except Exception:
            # Se a imagem falhar ao carregar, reposiciona o título à esquerda.
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

    # Linha horizontal separando o cabeçalho do conteúdo.
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
        # Colunas e larguras (mm) mudam conforme exiba ou não o guichê.
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
        # 'alt' alterna o fundo das linhas (efeito zebra) para legibilidade.
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
            alt = not alt  # inverte a cor de fundo para a próxima linha

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
    # Vai em página própria por poder ser longo e usa fonte monoespaçada
    # (Courier) para preservar o alinhamento original do log.
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
                # Ignora linhas problemáticas para não abortar o PDF inteiro.
                pass

    try:
        pdf.output(caminho)
        return True, ""
    except Exception as e:
        return False, str(e)
