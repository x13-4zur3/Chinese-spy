const commands = [
  ["/balance", "Check your chips"],
  ["/daily", "Claim daily reward"],
  ["/leaderboard", "Top balances"],
  ["/coinflip bet choice", "50/50 bet on heads or tails"],
  ["/blackjack bet", "Play blackjack with hit / stand / double"],
  ["/poker bet", "Texas Hold'em showdown vs bot"],
  ["/settings", "Server settings menu"],
  ["/setup", "Quick setup guide"],
  ["/help", "Command list"],
  ["/kick, /ban, /timeout, /purge", "Moderation tools"]
];

const tableBody = document.getElementById("command-list");

if (tableBody) {
  tableBody.innerHTML = commands
    .map(
      ([command, description]) => `
        <tr>
          <td><code>${command}</code></td>
          <td>${description}</td>
        </tr>
      `
    )
    .join("");
}
