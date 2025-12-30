// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Airdrop
/// @notice Demo contract with an intentional unbounded-loop gas footgun.
contract Airdrop {
    address public owner;
    address[] public recipients;
    mapping(address => uint256) public balances;

    constructor() {
        owner = msg.sender;
    }

    /// Cheap: a single storage write, no loops.
    function setOwner(address newOwner) external {
        require(msg.sender == owner, "not owner");
        owner = newOwner;
    }

    /// Bounded: fixed iteration count, considered safe.
    function seedFirstFive(address a) external {
        for (uint256 i = 0; i < 5; i++) {
            recipients.push(a);
        }
    }

    /// UNBOUNDED: loops over a dynamic array and writes storage each pass.
    function distribute(uint256 amount) external {
        require(msg.sender == owner, "not owner");
        for (uint256 i = 0; i < recipients.length; i++) {
            balances[recipients[i]] += amount;
        }
    }

    /// UNBOUNDED: while loop with no constant bound.
    function clearAll() external {
        require(msg.sender == owner, "not owner");
        while (recipients.length > 0) {
            address r = recipients[recipients.length - 1];
            balances[r] = 0;
            recipients.pop();
        }
    }
}
