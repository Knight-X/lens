import numpy as np

import subprocess
import random
import os
import struct
import parse
import socket
HOST = '127.0.0.1'
PORT = 1992
os.environ["CUDA_VISIBLE_DEVICES"] = "3"
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((HOST, PORT))


class Player:
  def __init__(self, log_dir="./data/log/"):
      self._iter = 1
      self._log_dir = log_dir

  def reset(self):
      return;

  def step(self):
      return;
      


class RandomPlayer(Player):
  def __init__(self, log_dir):
    Player.__init__(self, log_dir)
    self._total_reward = 0.0
    self._sock = sock
    self._sock.listen(5)
    f = open('rlconfig', 'r')
    self._llc = f.readline().split(' ')[2].replace("\n", "")
    self._src = f.readline().split(' ')[2].replace("\n", "")
    self._target = f.readline().split(' ')[2].replace("\n", "")
    f.close()

  def reset(self):
      self._iter = 1
      self._p = subprocess.Popen([self._llc, '-debug-only=regallocdl', '--regalloc=drl', self._src, '-o', self._target],shell=False, stdout=subprocess.PIPE)

  def step(self):
    terminal = False
    actions = set()
    maxlength = 0
    while (terminal == False):
      print "start accept " + str(self._iter)
      conn, addr = self._sock.accept()
      data = conn.recv(1024)
      if (data[0] == 'e'):
        terminal = True
        break
      reward_map, sortedr, slotend = self.getState(data)
      maxlength = max(slotend, maxlength)
      action, score = self.doAction(sortedr)
      conn.send(str(action))
      self._iter = self._iter + 1
      self._total_reward = self._total_reward + int(score)
      for g in reward_map.keys():
        actions.add(g)

    print "the totalreward is " + str(self._total_reward)
    self._iter = 1 
    self._total_reward = 0.0
    self.terminate()
    return actions, maxlength

  def getState(self, data):

      data = struct.unpack("!i", data)[0]
      if int(data) != self._iter:
          print "c++ iter: " + data + " python iter: " + str(self._iter)
          sys.exit(0)
      state, reward_map, sortedr, maxlength, _ = parse.fileToImage("state.txt", self._iter)
      return reward_map, sortedr, maxlength

  def doAction(self, reward_map):
      action = reward_map[-1][0]
      score = reward_map[-1][1]
      return action, score 

  def terminate(self):
    self._p.terminate()
    self._p.wait()
    print "process finish"

class Gplayer(Player):
  def __init__(self, idx2regs, regs2idx, maxlength, tofile, log_dir):
    Player.__init__(self, log_dir)
    self._sock = sock
    self._sock.listen(5)
    self._idx2Regs = idx2regs
    self._regs2idx = regs2idx
    self._maxlength = maxlength + 1
    self._actionsize = len(idx2regs)
    self._tofile = tofile
    f = open('rlconfig', 'r')
    self._llc = f.readline().split(' ')[2].replace("\n", "")
    self._src = f.readline().split(' ')[2].replace("\n", "")
    self._target = f.readline().split(' ')[2].replace("\n", "")
    f.close()

  def terprocess(self):
      print "terminal the process in python"
      #self._p.terminate()
      self._p.wait()

  def reset(self):
    self._p = subprocess.Popen([self._llc, '-debug-only=regallocdl', '--regalloc=drl', self._src, '-o', self._target],shell=False, stdout=subprocess.PIPE)
    print "start accept " + str(self._iter)
    self._iter = 1
    self._conn, addr = self._sock.accept()
    data = self._conn.recv(1024)
    state, reward_map = self.getState(data)
    return state, reward_map

  def step(self, action):
    #for log action data

    self.log(action)
    #prepare action and send action
    action = self._idx2Regs[action]
    self._conn.send(str(action))
    self._iter = self._iter + 1
    self._conn, addr = self._sock.accept()
    data = self._conn.recv(1024)
    if data[0] == 'e':
        self.terprocess()
        return [], True, []

    #get the next state after do action 
    state, reward_map = self.getState(data)
    return state, False, reward_map

  def getState(self, data):
    data = struct.unpack("!i", data)[0]
    # unpack the socket data to test if it is terminated 
    if int(data) != self._iter:
      print "c++ iter: " + data + " python iter: " + str(self._iter)
      sys.exit(0)

    # parse the state data which is outputed from compiler
    state, reward_map, _ = parse.getstate("state.txt", self._iter, self._maxlength, self._actionsize, self._regs2idx, self._tofile)
    return state, reward_map

  # test the action is valid
  def among(self, distri, reward_map, ac, valid):
    ac = self._idx2Regs[ac]
    if valid and reward_map.get(str(ac)) != None:
        reward = reward_map[str(ac)]
        ac = self._regs2idx[str(ac)]
        return int(reward), ac, True
    elif valid and reward_map.get(str(ac)) == None:
        ac = self._regs2idx[str(ac)]
        return 0.000001, ac, False
    elif not valid and reward_map.get(str(ac)) != None:
        reward = reward_map[str(ac)]
        ac = self._regs2idx[str(ac)]
        return int(reward), ac, True

    # find the register which is in the candidate list
    finalidx2reg = {}
    index = 0
    actions = [] 
    for i in self._regs2idx.keys():
        if reward_map.get(str(i)) != None:
            actions.insert(index, distri[self._regs2idx[str(i)]])
            finalidx2reg[str(index)] = i
            index = index + 1   
    #the comment part is the epislon greedy
    #if random.random() < 0.05:
    actions = softmax(actions)
    action = np.random.choice(index, 1, p=actions)
    action = action[0]
    #else:
    #  actions = softmax(actions)
    #  action = np.random.choice(index, 1, p=actions)
    #  action = action[0]
      #action = np.argmax(np.array(actions))
    action = finalidx2reg[str(action)]
    reward = reward_map[str(action)]
    action = self._regs2idx[str(action)]
    return int(reward), action, True

  def log(self, action):
    name = self._log_dir + "action" + str(self._iter) + ".txt"
    f = open(name, "w")
    f.write(str(action))
    f.close()



# helper function for simple reinforcement learning example 
def among(distri, ac, valid):
    reward_map = {"1": 3, "0": 5}
    if valid and reward_map.get(str(ac)) != None:
        return ac, True
    elif valid and reward_map.get(str(ac)) == None:
        return ac, False
    elif not valid and reward_map.get(str(ac)) != None:
        return ac, True
    
    index = 2 
    actions = []
    for i in range(index):
        actions.append(distri[0][i])
    #if random.random() < 0.0005:
    actions = softmax(actions)
    action = np.random.choice(index, 1, p=actions)
    action = action[0]
    #else:
    #action = np.argmax(np.array(actions))
    return action, True

def softmax(x):
    x = x - np.max(x)
    exp_x = np.exp(x)
    softmax_x = exp_x / np.sum(exp_x)
    return softmax_x
