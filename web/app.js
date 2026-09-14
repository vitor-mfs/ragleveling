/* ragleveling — mesma lógica da CLI, rodando no navegador sobre os dados
   exportados por scripts/export_web.py. */

(function () {
  "use strict";

  var DADOS = window.RAGLEVELING_DATA;

  /* --- fórmula de EXP do Renewal: penalidade por diferença de nível --- */

  var PENALIDADE = {
    "-15": 0.10, "-14": 0.20, "-13": 0.30, "-12": 0.40, "-11": 0.50,
    "-10": 0.60, "-9": 0.70, "-8": 0.80, "-7": 0.90, "-6": 1.00,
    "-5": 1.00, "-4": 1.00, "-3": 1.00, "-2": 1.00, "-1": 1.00,
    "0": 1.00, "1": 1.00, "2": 1.00, "3": 1.00, "4": 1.00, "5": 1.00,
    "6": 1.05, "7": 1.10, "8": 1.15, "9": 1.20, "10": 1.25,
    "11": 1.30, "12": 1.35, "13": 1.40, "14": 1.45, "15": 1.50
  };

  function expRate(diff) {
    if (diff < -15) return PENALIDADE["-15"];
    if (diff > 15) return PENALIDADE["15"];
    return PENALIDADE[String(diff)];
  }

  /* --- elementos --- */

  var ELEMENTOS = ["Neutral", "Water", "Earth", "Fire", "Wind", "Poison", "Holy", "Dark", "Ghost", "Undead"];
  var ELEMENTO_PT = {
    Neutral: "Neutro", Water: "Água", Earth: "Terra", Fire: "Fogo", Wind: "Vento",
    Poison: "Veneno", Holy: "Sagrado", Dark: "Sombrio", Ghost: "Fantasma", Undead: "Morto-vivo"
  };
  var RACA_PT = {
    Formless: "Amorfo", Undead: "Morto-vivo", Brute: "Bruto", Plant: "Planta", Insect: "Inseto",
    Fish: "Peixe", Demon: "Demônio", DemiHuman: "Demi-humano", Angel: "Anjo", Dragon: "Dragão", Player: "Jogador"
  };
  var TAMANHO_PT = { Small: "Pequeno", Medium: "Médio", Large: "Grande" };

  var NIVEIS_ELEMENTO = Object.keys(DADOS.attr_fix).map(Number).sort(function (a, b) { return a - b; });

  function nivelValido(nivel) {
    if (DADOS.attr_fix[nivel]) return nivel;
    return NIVEIS_ELEMENTO.reduce(function (melhor, n) {
      return Math.abs(n - nivel) < Math.abs(melhor - nivel) ? n : melhor;
    }, NIVEIS_ELEMENTO[0]);
  }

  function rankingElemental(elementoDefesa, nivelDefesa) {
    var tabela = DADOS.attr_fix[nivelValido(nivelDefesa)] || {};
    return ELEMENTOS
      .filter(function (ataque) { return tabela[ataque]; })
      .map(function (ataque) {
        var pct = tabela[ataque][elementoDefesa];
        return { elemento: ataque, pct: typeof pct === "number" ? pct : 100 };
      })
      .sort(function (a, b) { return b.pct - a.pct; });
  }

  /* --- classes --- */

  var MUNICAO = { Gunslinger: 1, Rebellion: 1, Night_Watch: 1 };

  function comoAplicar(classeKey, perfil, elementoPt) {
    if (perfil === "magic") return "magia de " + elementoPt;
    if (MUNICAO[classeKey]) return "munição de " + elementoPt;
    if (perfil === "ranged") return "flecha de " + elementoPt;
    return "carta de " + elementoPt + " na arma ou Encantar Arma";
  }

  /* --- dificuldade --- */

  var CATEGORIAS_LEVES = { "dano forte": 1, "buff próprio": 1 };

  function normalizar(valores) {
    var menor = Math.min.apply(null, valores);
    var maior = Math.max.apply(null, valores);
    if (!(maior > menor)) return valores.map(function () { return 0; });
    return valores.map(function (v) { return (v - menor) / (maior - menor); });
  }

  var PESOS = { hp: 0.30, defesa: 0.20, ataque: 0.20, perigo: 0.20, quantidade: 0.10 };
  var SOMA_PESOS = PESOS.hp + PESOS.defesa + PESOS.ataque + PESOS.perigo + PESOS.quantidade;

  function pontuar(monstros, perfil) {
    var chaveDefesa = perfil === "magic" ? "mdef" : "def";
    var hp = normalizar(monstros.map(function (m) { return m.hp; }));
    var defesa = normalizar(monstros.map(function (m) { return m[chaveDefesa]; }));
    var ataque = normalizar(monstros.map(function (m) { return m.atk; }));
    var perigo = normalizar(monstros.map(function (m) { return m.sw; }));
    var quantidade = normalizar(monstros.map(function (m) { return Object.keys(m.sc).length; }));

    return monstros.map(function (_, i) {
      var bruto = (hp[i] * PESOS.hp + defesa[i] * PESOS.defesa + ataque[i] * PESOS.ataque +
        perigo[i] * PESOS.perigo + quantidade[i] * PESOS.quantidade) / SOMA_PESOS;
      var score = Math.round(bruto * 1000) / 10;
      return { score: score, rotulo: score < 33 ? "facil" : (score < 66 ? "medio" : "dificil") };
    });
  }

  var ROTULO_PT = { facil: "fácil", medio: "médio", dificil: "difícil" };

  /* --- consulta --- */

  function filtrarSpawns(spawns, estado) {
    return spawns.filter(function (s) {
      var flag = s[3];
      if (flag === 1 && !estado.instancias) return false;
      if (flag === 2 && !estado.todosMapas) return false;
      return s[1] >= estado.minSpawn;
    });
  }

  function consultar(estado) {
    var minimo = estado.nivel + estado.faixaMin;
    var maximo = estado.nivel + estado.faixaMax;
    var busca = estado.busca.trim().toLowerCase();

    var candidatos = [];
    var spawnsPorMob = [];

    DADOS.monstros.forEach(function (m) {
      if (m.l < minimo || m.l > maximo) return;
      var spawns = filtrarSpawns(m.sp, estado);
      if (!spawns.length) return;
      if (busca) {
        var casa = m.n.toLowerCase().indexOf(busca) !== -1 ||
          spawns.some(function (s) { return s[0].indexOf(busca) !== -1; });
        if (!casa) return;
      }
      candidatos.push(m);
      spawnsPorMob.push(spawns);
    });

    if (!candidatos.length) return [];

    var scores = pontuar(candidatos, estado.perfil);

    var alvos = candidatos.map(function (m, i) {
      var diff = m.l - estado.nivel;
      var taxa = expRate(diff);
      var ranking = rankingElemental(m.e, m.el);
      var melhor = ranking[0];
      var piores = ranking.slice(-2).reverse();
      var melhorPt = ELEMENTO_PT[melhor.elemento];
      return {
        dados: m,
        spawns: spawnsPorMob[i],
        diff: diff,
        taxa: taxa,
        expEfetiva: m.be * taxa,
        jobEfetiva: m.je * taxa,
        dificuldade: scores[i],
        melhorElemento: melhor,
        melhorElementoPt: melhorPt,
        piores: piores,
        aplicar: comoAplicar(estado.classeKey, estado.perfil, melhorPt)
      };
    });

    var ordens = {
      dificuldade: function (a, b) { return a.dificuldade.score - b.dificuldade.score || b.expEfetiva - a.expEfetiva; },
      exp: function (a, b) { return b.expEfetiva - a.expEfetiva; },
      nivel: function (a, b) { return a.dados.l - b.dados.l || a.dificuldade.score - b.dificuldade.score; }
    };
    alvos.sort(ordens[estado.ordenar]);
    return alvos;
  }

  /* --- interface --- */

  var DP_URL = "https://www.divine-pride.net/database/monster/";

  var el = function (id) { return document.getElementById(id); };
  var nf = new Intl.NumberFormat("pt-BR");

  var estado = {
    nivel: 60,
    classeKey: "Rune_Knight",
    perfilEscolhido: "auto",
    perfil: "melee",
    ordenar: "dificuldade",
    faixaMin: -5,
    faixaMax: 15,
    minSpawn: 5,
    busca: "",
    instancias: false,
    todosMapas: false
  };

  var perfilPorClasse = {};
  DADOS.classes.forEach(function (c) { perfilPorClasse[c.k] = c.perfil; });

  function montarClasses() {
    var select = el("classe");
    DADOS.classes.forEach(function (c) {
      var opcao = document.createElement("option");
      opcao.value = c.k;
      opcao.textContent = c.nome;
      if (c.k === estado.classeKey) opcao.selected = true;
      select.appendChild(opcao);
    });
  }

  function resolverPerfil() {
    estado.perfil = estado.perfilEscolhido === "auto"
      ? (perfilPorClasse[estado.classeKey] || "melee")
      : estado.perfilEscolhido;
  }

  function chipElemento(elemento, sufixo) {
    return '<span class="chip" style="--cor-el: var(--el-' + elemento + ')">' +
      ELEMENTO_PT[elemento] + (sufixo || "") + "</span>";
  }

  function textoPerigos(categorias) {
    return Object.keys(categorias).filter(function (c) { return !CATEGORIAS_LEVES[c]; }).join(", ");
  }

  function linhaDetalhe(alvo) {
    var m = alvo.dados;
    var mapas = alvo.spawns.map(function (s) {
      var respawn = s[2] ? " · " + Math.round(s[2] / 1000) + "s" : "";
      var origem = s[4] ? " <span class='pct'>manual</span>" : "";
      return "<li class='mono'>" + s[0] + " — " + s[1] + " mobs" + respawn + origem + "</li>";
    }).join("");

    var skills = Object.keys(m.sc).map(function (c) {
      return "<li>" + c + " <span class='pct'>×" + m.sc[c] + "</span></li>";
    }).join("") || "<li class='pct'>nenhuma habilidade registrada</li>";

    var evitar = alvo.piores.map(function (p) {
      return "<li>" + chipElemento(p.elemento) + " <span class='pct'>" + p.pct + "%</span></li>";
    }).join("");

    return '<tr class="detalhe"><td colspan="11"><div class="detalhe-grid">' +
      "<div><h4>Onde nasce</h4><ul>" + mapas + "</ul></div>" +
      "<div><h4>Habilidades</h4><ul>" + skills + "</ul></div>" +
      "<div><h4>Não use</h4><ul>" + evitar + "</ul></div>" +
      "<div><h4>Ficha</h4><ul>" +
        "<li>" + RACA_PT[m.r] + " · " + TAMANHO_PT[m.sz] + "</li>" +
        "<li>ATK <span class='mono'>" + nf.format(m.atk) + "</span> · DEF <span class='mono'>" + m.def +
        "</span> · MDEF <span class='mono'>" + m.mdef + "</span></li>" +
        "<li>Job EXP <span class='mono'>" + nf.format(Math.round(alvo.jobEfetiva)) + "</span></li>" +
        "<li>Contra ele: <strong>" + alvo.aplicar + "</strong></li>" +
        '<li><a href="' + DP_URL + m.id + '" target="_blank" rel="noopener">Divine Pride ↗</a> ' +
          "<span class='pct'>#" + m.id + "</span></li>" +
      "</ul></div></div></td></tr>";
  }

  function render() {
    resolverPerfil();
    var alvos = consultar(estado);
    var corpo = el("corpo");
    var vazio = el("vazio");

    el("thDefesa").textContent = estado.perfil === "magic" ? "MDEF" : "DEF";

    if (!alvos.length) {
      corpo.innerHTML = "";
      el("tabela").hidden = true;
      vazio.hidden = false;
      vazio.textContent = "Nenhum monstro com esses filtros. Alargue a faixa de nível, baixe o mínimo por mapa ou limpe a busca.";
      el("resumo").innerHTML = "";
      return;
    }

    el("tabela").hidden = false;
    vazio.hidden = true;

    var melhorExp = alvos.reduce(function (a, b) { return a.expEfetiva > b.expEfetiva ? a : b; });
    el("resumo").innerHTML =
      "<span><b>" + alvos.length + "</b> alvos</span>" +
      "<span>níveis <b>" + (estado.nivel + estado.faixaMin) + "–" + (estado.nivel + estado.faixaMax) + "</b></span>" +
      "<span>mais EXP: <b>" + melhorExp.dados.n + "</b> (" + nf.format(Math.round(melhorExp.expEfetiva)) + ")</span>" +
      "<span>defesa avaliada: <b>" + (estado.perfil === "magic" ? "MDEF" : "DEF") + "</b></span>" +
      '<span class="legenda"><i class="facil">fácil</i><i class="medio">médio</i><i class="dificil">difícil</i></span>';

    corpo.innerHTML = alvos.slice(0, 60).map(function (alvo, i) {
      var m = alvo.dados;
      var principal = alvo.spawns[0];
      var extras = alvo.spawns.length - 1;
      var defesa = estado.perfil === "magic" ? m.mdef : m.def;
      var perigos = textoPerigos(m.sc);
      var rot = alvo.dificuldade.rotulo;

      return '<tr class="linha-alvo" data-i="' + i + '" tabindex="0">' +
        '<td class="stripe bg-' + rot + '"></td>' +
        '<td class="nome"><a href="' + DP_URL + m.id + '" target="_blank" rel="noopener">' + m.n +
          '</a><span class="lv">lv ' + m.l + "</span></td>" +
        '<td class="num">' + (alvo.diff >= 0 ? "+" : "") + alvo.diff +
          ' <span class="pct">' + Math.round(alvo.taxa * 100) + "%</span></td>" +
        '<td class="num">' + nf.format(Math.round(alvo.expEfetiva)) + "</td>" +
        '<td class="num">' + nf.format(m.hp) + "</td>" +
        '<td class="num">' + defesa + "</td>" +
        '<td class="num dif ' + rot + '" title="' + ROTULO_PT[rot] + '">' +
          Math.round(alvo.dificuldade.score) + "</td>" +
        '<td class="perigo">' + (perigos ? "<em>" + perigos + "</em>" : "—") + "</td>" +
        '<td class="mapa">' + principal[0] + (principal[4] ? "*" : "") + " (" + principal[1] + ")" +
          (extras > 0 ? ' <span class="mais">+' + extras + "</span>" : "") + "</td>" +
        "<td>" + chipElemento(m.e, " " + m.el) + "</td>" +
        "<td>" + chipElemento(alvo.melhorElemento.elemento) +
          ' <span class="pct">' + alvo.melhorElemento.pct + "%</span></td>" +
        "</tr>";
    }).join("");

    corpo.__alvos = alvos;
  }

  function alternarDetalhe(linha) {
    var seguinte = linha.nextElementSibling;
    if (seguinte && seguinte.classList.contains("detalhe")) {
      seguinte.remove();
      return;
    }
    var abertos = document.querySelectorAll("tr.detalhe");
    Array.prototype.forEach.call(abertos, function (tr) { tr.remove(); });
    var alvo = el("corpo").__alvos[Number(linha.dataset.i)];
    linha.insertAdjacentHTML("afterend", linhaDetalhe(alvo));
  }

  /* --- ligações --- */

  function numeroDe(input, minimo, maximo, padrao) {
    var valor = parseInt(input.value, 10);
    if (isNaN(valor)) return padrao;
    return Math.min(maximo, Math.max(minimo, valor));
  }

  montarClasses();
  el("totalMonstros").textContent = nf.format(DADOS.monstros.length);

  el("nivel").addEventListener("input", function () {
    estado.nivel = numeroDe(this, 1, 260, 60);
    render();
  });

  el("classe").addEventListener("change", function () {
    estado.classeKey = this.value;
    render();
  });

  ["perfil", "ordenar"].forEach(function (grupo) {
    el(grupo).addEventListener("click", function (evento) {
      var botao = evento.target.closest("button");
      if (!botao) return;
      Array.prototype.forEach.call(this.querySelectorAll("button"), function (b) {
        b.setAttribute("aria-pressed", String(b === botao));
      });
      if (grupo === "perfil") estado.perfilEscolhido = botao.dataset.valor;
      else estado.ordenar = botao.dataset.valor;
      render();
    });
  });

  el("faixaMin").addEventListener("input", function () {
    estado.faixaMin = numeroDe(this, -100, 100, -5);
    render();
  });

  el("faixaMax").addEventListener("input", function () {
    estado.faixaMax = numeroDe(this, -100, 100, 15);
    render();
  });

  el("minSpawn").addEventListener("input", function () {
    estado.minSpawn = numeroDe(this, 1, 200, 5);
    render();
  });

  el("busca").addEventListener("input", function () {
    estado.busca = this.value;
    render();
  });

  el("instancias").addEventListener("change", function () {
    estado.instancias = this.checked;
    render();
  });

  el("todosMapas").addEventListener("change", function () {
    estado.todosMapas = this.checked;
    render();
  });

  el("corpo").addEventListener("click", function (evento) {
    if (evento.target.closest("a")) return;   // o link do Divine Pride não abre o detalhe
    var linha = evento.target.closest("tr.linha-alvo");
    if (linha) alternarDetalhe(linha);
  });

  el("corpo").addEventListener("keydown", function (evento) {
    if (evento.key !== "Enter" && evento.key !== " ") return;
    var linha = evento.target.closest("tr.linha-alvo");
    if (!linha) return;
    evento.preventDefault();
    alternarDetalhe(linha);
  });

  render();
})();
