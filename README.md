# Nebula

**Nebula é uma linguagem de programação criada para deixar o código mais legível e acessível.** Suas palavras-chave são escritas em português, permitindo que os programas se aproximem de instruções naturais sem abrir mão de conceitos comuns da programação, como variáveis, condições, laços de repetição, funções, listas e classes.

Este guia é para quem está começando a usar Nebula ou aprendendo programação. Você não precisa entender como o interpretador funciona para começar a escrever seus próprios programas.

> Nebula continua em desenvolvimento. Alguns recursos e comandos podem mudar entre versões. Se algo funcionar de forma diferente na sua instalação, consulte os exemplos incluídos na mesma versão.

## Conteúdo

- [Começando](#começando)
- [Seu primeiro programa](#seu-primeiro-programa)
- [Executando um programa](#executando-um-programa)
- [Shell interativo](#shell-interativo)
- [Variáveis e valores](#variáveis-e-valores)
- [Exibindo informações e recebendo dados](#exibindo-informações-e-recebendo-dados)
- [Listas](#listas)
- [Condições](#condições)
- [Laços de repetição](#laços-de-repetição)
- [Funções](#funções)
- [Classes e objetos](#classes-e-objetos)
- [Módulos e importações](#módulos-e-importações)
- [Verificando seu código](#verificando-seu-código)
- [Suporte em editores](#suporte-em-editores)
- [Erros comuns de iniciantes](#erros-comuns-de-iniciantes)
- [Exemplos incluídos no Nebula](#exemplos-incluídos-no-nebula)
- [Dicas para aprender](#dicas-para-aprender)

## Começando

### 1. Obtenha o Nebula

Baixe ou obtenha uma versão do Nebula pelo canal em que o projeto é distribuído. Se a versão incluir um instalador para Windows, execute-o e siga as instruções.

Se você recebeu o Nebula em um arquivo compactado com o código-fonte, extraia os arquivos antes de começar. O projeto inclui exemplos de programas e os arquivos necessários para executar a linguagem.

### 2. Confira se está funcionando

Abra o **Prompt de Comando** ou o **PowerShell** e tente executar:

```bat
nebula --verificar examples\ola.neb
```

Esse comando verifica o arquivo de exemplo sem executá-lo. Ele pressupõe que o Nebula esteja instalado e disponível no `PATH` do terminal e que você esteja na pasta do projeto — ou que informe o caminho correto do arquivo.

Se o Windows disser que `nebula` não é reconhecido, o executável ou script de inicialização pode não estar no `PATH`. Tente abrir um novo terminal depois da instalação. Se o problema continuar, confira a pasta de instalação ou use o iniciador incluído na sua versão.

## Seu primeiro programa

Crie um arquivo chamado `ola.neb` e escreva:

```text
falar("Olá, mundo!")
```

Salve o arquivo. Pronto: você escreveu seu primeiro programa em Nebula!

- `falar(...)` exibe informações no terminal.
- O texto entre aspas é uma *string* (texto).
- Os parênteses contêm a informação passada para a função.

O resultado deve ser parecido com isto:

```text
Olá, mundo!
```

## Executando um programa

Os arquivos de código-fonte do Nebula usam a extensão `.neb`.

Abra um terminal na pasta em que seu arquivo está salvo e execute:

```bat
nebula ola.neb
```

Se o arquivo estiver em outra pasta, informe o caminho:

```bat
nebula "C:\Users\SeuNome\Documents\ola.neb"
```

### Comandos úteis

| Comando | O que faz |
| --- | --- |
| `nebula arquivo.neb` | Executa um programa Nebula. |
| `nebula --verificar arquivo.neb` | Verifica o programa sem executá-lo. |
| `nebula --shell` | Abre o shell interativo. |
| `nebula setmain arquivo.neb` | Define o arquivo principal usado pelo comando `nebula .`. |
| `nebula .` | Executa o arquivo principal configurado, caso tenha sido definido. |

Troque `arquivo.neb` pelo nome ou caminho do seu arquivo. No Windows, a versão também pode incluir scripts de inicialização, como `nebula.bat` ou `nebula-run.bat`.

## Shell interativo

O shell interativo permite testar pequenos trechos de código sem precisar criar um arquivo para cada experimento.

Abra-o com:

```bat
nebula --shell
```

Use o shell para experimentar expressões e recursos da linguagem. Para programas maiores, salve o código em um arquivo `.neb`, assim você poderá editá-lo e executá-lo novamente depois.

## Variáveis e valores

Uma **variável** é um nome associado a um valor. Ela permite guardar uma informação e utilizá-la mais tarde.

No Nebula, `declarar` é usado para declarar uma variável:

```text
declarar nome como "Ana"
declarar idade como 14
declarar ativo como verdadeiro
```

Nesse exemplo, `nome` guarda um texto, `idade` guarda um número e `ativo` guarda um valor lógico, que pode ser verdadeiro ou falso.

Alguns tipos comuns de valores:

| Tipo | Exemplo | Significado |
| --- | --- | --- |
| Texto (*string*) | `"Olá!"` | Uma sequência de caracteres. |
| Número | `42`, `3.14` | Um valor numérico. |
| Lógico (*booleano*) | `verdadeiro`, `falso` | Um valor verdadeiro ou falso. |
| Lista | `[]` | Uma coleção de valores. |

Escolha nomes que expliquem o que cada variável guarda. Por exemplo, `pontuacao` costuma ser mais claro do que `x` quando a variável armazena uma pontuação.

## Exibindo informações e recebendo dados

Use `falar(...)` para mostrar um valor:

```text
declarar nome como "Ana"
falar("Olá, ")
falar(nome)
```

Você pode exibir textos, variáveis e outros valores para conferir o que o programa está fazendo.

Se sua versão tiver uma função para receber dados digitados pelo usuário, consulte os exemplos ou a ajuda da versão instalada para descobrir o nome e a forma de uso. Este README não presume um nome para essa função que possa ser diferente entre versões.

## Listas

Uma lista guarda vários valores dentro de uma única variável. Para criar uma lista vazia, use `[]`:

```text
declarar frutas como []
```

Você pode adicionar itens usando o método `colocar` da lista:

```text
frutas.colocar("maçã")
frutas.colocar("banana")

falar(frutas)
```

Listas são úteis para guardar informações relacionadas, como nomes, pontuações, itens de inventário ou uma sequência de tarefas.

Outro exemplo:

```text
declarar pontuacoes como []

pontuacoes.colocar(10)
pontuacoes.colocar(25)
pontuacoes.colocar(18)

falar(pontuacoes)
```

As operações disponíveis para listas podem variar conforme a versão do Nebula e sua biblioteca padrão.

## Condições

As condições permitem que um programa escolha o que fazer de acordo com uma situação.

Uma estrutura condicional costuma usar `se` para testar uma condição e `senão` para indicar uma alternativa. A sintaxe exata dos blocos depende da versão do Nebula; use os exemplos que acompanham sua instalação como referência para escrever uma condição completa.

Conceitualmente, um programa poderia fazer o seguinte:

```text
se idade >= 18 faça
    falar("Maior de idade")
senão
    falar("Menor de idade")
fim
```

Esse exemplo ilustra a ideia de uma condição. Se sua versão indicar um erro de sintaxe, compare a estrutura com os exemplos atuais da pasta `examples`, pois a sintaxe pode mudar entre versões.

## Laços de repetição

Laços de repetição permitem executar instruções várias vezes. Eles são úteis quando você precisa percorrer uma lista ou repetir uma tarefa.

Por exemplo, um laço `para cada` expressa a ideia de fazer algo para cada item de uma coleção:

```text
declarar nomes como []

nomes.colocar("Ana")
nomes.colocar("Leo")

para cada nome em nomes.__valores faça
    falar(nome)
fim
```

Esse exemplo usa a forma de laço presente nos exemplos do Nebula e acessa os valores da lista por meio de `__valores`. Os recursos para trabalhar com coleções podem evoluir, então confira os exemplos da sua versão se precisar de outro tipo de repetição.

## Funções

Funções agrupam instruções com um nome para que possam ser reutilizadas. No Nebula, declarações de função usam `função`, e os parâmetros são introduzidos com `usando`.

Uma função pode ser escrita assim:

```text
função cumprimentar usando (nome)
    falar("Olá, ")
    falar(nome)
fim
```

O parâmetro `nome` representa um valor que será fornecido à função quando ela for chamada. Depois de declarar a função, utilize a sintaxe de chamada aceita pela sua versão do Nebula.

Funções ajudam a organizar o programa: em vez de copiar as mesmas instruções em vários lugares, você pode reuni-las em uma função reutilizável.

Algumas funções podem devolver um resultado usando `retornar`. Por exemplo, uma função que calcula um total pode retornar a resposta, em vez de exibi-la imediatamente.

## Classes e objetos

Uma **classe** descreve um tipo de objeto. Um objeto pode guardar informações (atributos) e oferecer funções (métodos) que trabalham com essas informações.

No Nebula, `classe` declara uma classe. Um método semelhante a um construtor pode usar `principal`, e `esse` se refere ao objeto atual.

```text
classe Item
    função principal usando (esse, nome, preço)
        esse.nome = nome
        esse.preço = preço
    fim
fim
```

Nesse exemplo, um `Item` possui um `nome` e um `preço`. As atribuições guardam esses valores no objeto atual.

Outra classe pode guardar uma lista de itens:

```text
classe Cesta
    função principal usando (esse)
        esse.items = []
    fim

    função adicionar usando (esse, val)
        esse.items.colocar(val)
    fim

    função ver usando (esse) => retornar esse.items
fim
```

Classes são úteis quando seu programa precisa representar coisas com dados e comportamentos relacionados — por exemplo, um jogador, um produto, uma cesta de compras ou um personagem de jogo.

Versões do Nebula podem oferecer outros recursos de orientação a objetos, incluindo herança. Consulte `examples/heranca.neb` para ver um exemplo incluído no projeto.

## Módulos e importações

Módulos permitem reutilizar código de outro arquivo, sem precisar colocar tudo em um único programa. O Nebula inclui módulos da biblioteca padrão, mas a sintaxe exata de importação e os nomes dos módulos disponíveis dependem da versão.

O projeto inclui módulos como `listas` e `matematica`. Confira os arquivos em `src/stdlib` e os programas de exemplo para descobrir quais recursos estão disponíveis e como importá-los na versão atual.

## Verificando seu código

Se o programa não executar, comece verificando-o sem rodar o código:

```bat
nebula --verificar meu_programa.neb
```

Leia a mensagem de erro com atenção. Ela pode indicar uma linha e mostrar onde o Nebula encontrou um problema.

Um bom fluxo de trabalho para iniciantes é:

1. Faça uma pequena alteração.
2. Salve o arquivo.
3. Execute `nebula --verificar meu_programa.neb`.
4. Corrija os erros de sintaxe indicados.
5. Execute `nebula meu_programa.neb` para testar o programa.

Um programa pode passar pela verificação de sintaxe e ainda se comportar de maneira diferente da esperada. A verificação não garante que a lógica do programa esteja correta.

## Suporte em editores

O projeto inclui uma extensão para VS Code na pasta `vscode-nebula`. Ela oferece recursos específicos para editar Nebula. Consulte o README dessa pasta para ver como instalar a extensão e quais recursos estão disponíveis na sua versão.

O projeto também inclui um servidor de linguagem (LSP), que pode oferecer recursos de editor, como diagnósticos e navegação pelo código. Esses recursos dependem do editor e de como a extensão está configurada para utilizar as ferramentas do Nebula.

## Erros comuns de iniciantes

- **Esquecer as aspas:** textos precisam de aspas, como `"Olá"`.
- **Usar a extensão errada:** salve os programas Nebula com a extensão `.neb`.
- **Executar o comando na pasta errada:** entre na pasta que contém o arquivo ou informe o caminho completo.
- **Confundir um texto com uma variável:** `"nome"` é a palavra literal `nome`; `nome` se refere à variável.
- **Presumir que outra linguagem funciona igual:** Nebula tem suas próprias palavras-chave e sintaxe. Consulte os exemplos em vez de presumir que o código de Python, JavaScript ou outra linguagem funcionará.
- **Ignorar o primeiro erro:** corrija primeiro o erro de sintaxe que aparece inicialmente. Outros erros podem ser consequência dele.
- **Supor que todo recurso existe em todas as versões:** use os exemplos e o histórico de alterações incluídos na sua versão como referência.

## Exemplos incluídos no Nebula

O projeto inclui programas de exemplo que você pode abrir, estudar e executar:

| Arquivo | O que explorar |
| --- | --- |
| `examples/ola.neb` | Um programa inicial simples. |
| `examples/tipos.neb` | Exemplos envolvendo valores e tipos. |
| `examples/vetor.neb` | Listas ou coleções semelhantes a vetores. |
| `examples/heranca.neb` | Classes e herança. |

Se você está começando a programar, abra `ola.neb` primeiro. Altere o texto, execute novamente e depois explore os outros exemplos aos poucos. Aprender modificando um programa que já funciona costuma ser mais fácil do que começar com uma página em branco.

## Dicas para aprender

- Comece com programas pequenos, que façam apenas uma coisa.
- Use nomes que descrevam o que cada variável guarda.
- Teste com frequência, em vez de escrever um programa enorme de uma vez.
- Quando encontrar uma palavra-chave desconhecida, procure outros exemplos de uso no projeto.
- Guarde cópias dos programas que funcionam para comparar com versões que apresentem problemas.

**Boas-vindas ao Nebula!** A melhor maneira de aprender é escrever um pouco de código, executar, observar o resultado e continuar experimentando.
