import cv2, serial, time, os, re
from numpy import *
import arena,ui,dm
from utils import *
   
###############
## SETUP
###############
Arena = arena.Arena()
ui = ui.UI()

cv2.namedWindow("ArenaScanner")
cv2.namedWindow("ArenaControlPanel")
cv2.startWindowThread()

allImg = None

#DataMatrix  
dm = dm.DM((Arena.numbots + 4 + (Arena.numzones-1)*2), 100)

poi_pattern = re.compile('^C(\d)$')
bot_pattern = re.compile('^(\d{2})$')

cv2.createTrackbar('Scan (ms)', 'ArenaControlPanel', dm.timeout, 1000, dm.setTimeout)
cv2.createTrackbar('Threshold', 'ArenaControlPanel', Arena.threshold, 255, Arena.setThreshold)
cv2.setMouseCallback("ArenaControlPanel", ui.onMouse, (Arena,dm))

cornerSize = 4.1875
gap = 1.625

###############
## LOOP
###############
while True:
    for z in Arena.zone:
        #skip if capture is disabled
        if z.cap == -1:
            continue
            
        #get the next frame from the zones capture device
        success, origImg = z.cap.read()
        if not success:
            print("Error reading from camera: "+str(z.vdi));
            ui.exit = True
            break;
        width = size(origImg, 1)
        height = size(origImg, 0)

        #Apply image transformations
        threshImg = cv2.cvtColor(origImg, cv2.COLOR_BGR2GRAY) #convert to grayscale
        ret,threshImg = cv2.threshold(threshImg, Arena.threshold, 255, cv2.THRESH_BINARY)
        
        #Start Output Image
        if ui.isDisplayed(z.id):
            if ui.displayMode >= 2:
                outputImg = zeros((height, width, 3), uint8) #create a blank image
            elif ui.displayMode == 0:
                outputImg = cv2.cvtColor(threshImg, cv2.COLOR_GRAY2BGR)
            else:
                outputImg = origImg;
            
        #Scan for DataMatrix
        xmin = z.scanarea[0][0] if z.scanarea[0][0] < z.scanarea[3][0] else z.scanarea[3][0]
        xmax = z.scanarea[1][0] if z.scanarea[1][0] > z.scanarea[2][0] else z.scanarea[2][0]
        ymin = z.scanarea[2][1] if z.scanarea[2][1] < z.scanarea[3][1] else z.scanarea[3][1]
        ymax = z.scanarea[0][1] if z.scanarea[0][1] > z.scanarea[1][1] else z.scanarea[1][1]
        dm.scan(origImg[ymin:ymax,xmin:xmax], offsetx = xmin, offsety = ymin)  
        #dm.scan(origImg)

        #For each detected DataMatrix symbol
        for content,symbol in dm.symbols:
            #Zone POI/Corners
            match = poi_pattern.match(content)
            if match:
                sval = int(match.group(1))
                for idx,poival in enumerate(z.poisymbol):
                    if sval == poival:
                        z.poi[idx] = symbol[idx]
                        
                        offset = int(gap * (symbol[1][0]-symbol[0][0]) / cornerSize)
                        scanarea_offset_scalar = 1.4
                    
                        offset_x_sign = 1 if (idx%3 != 0) else -1
                        offset_y_sign = 1 if (idx < 2) else -1
                        
                        z.poi[idx] = (z.poi[idx][0] + offset_x_sign * offset, z.poi[idx][1] + offset_y_sign * offset)
                        x_op_idx = abs(idx - 3)
                        y_op_idx = abs(idx - 5)%4
                        outcome_true_x_idx = idx if (idx%3 == 0) else x_op_idx
                        outcome_false_x_idx = idx if not (idx%3 == 0) else x_op_idx
                        outcome_true_y_idx = idx if (idx < 2) else y_op_idx
                        outcome_false_y_idx = idx if not (idx < 2) else y_op_idx
                        
                        if Arena.numzones > 1 and z.id == int(idx%3==0):
                            x = z.poi[outcome_true_x_idx][0] + int(offset_x_sign * offset * scanarea_offset_scalar * 4)
                        elif z.poi[idx][0] < z.poi[x_op_idx][0]:
                            x = z.poi[outcome_true_x_idx][0] + int(offset_x_sign * offset * scanarea_offset_scalar)
                        else:
                            x = z.poi[outcome_false_x_idx][0] + int(offset_x_sign * offset * scanarea_offset_scalar)
                            
                        if z.poi[idx][1] > z.poi[y_op_idx][1]:
                            y = z.poi[outcome_true_y_idx][1] + int(offset_y_sign * offset * scanarea_offset_scalar)
                        else:
                            y = z.poi[outcome_false_y_idx][1] + int(offset_y_sign * offset * scanarea_offset_scalar)

                        if x > width:
                            x = width
                        elif x < 0:
                            x = 0
                        if y > height:
                            y = height
                        elif y < 0:
                            y = 0
                        
                        z.scanarea[idx] = (x, y)
                        
                        z.poitime[idx] = time.time()
                        if ui.isDisplayed(z.id) and ui.displayMode < 3:
                            drawBorder(outputImg, symbol, ui.COLOR_BLUE, 2)
                            pt = (symbol[1][0]-35, symbol[1][1]-25)  
                            cv2.putText(outputImg, str(sval), pt, cv2.FONT_HERSHEY_PLAIN, 1.5, ui.COLOR_BLUE, 2)
            
            #Bot Symbol
            match = bot_pattern.match(content)
            if match:
                botId = int(match.group(1))
                if botId < 0 or Arena.numbots <=botId:
                    continue
                bot = Arena.bot[botId]
                bot.setData(symbol, z, threshImg)    #update the bot's data
                if ui.isDisplayed(z.id) and ui.displayMode < 3:
                    bot.drawOutput(outputImg)   #draw the bot's symbol

        #Draw Objects on Scanner window if this zone is displayed
        if ui.isDisplayed(z.id):
            #Crosshair in center
            pt0 = (width/2,height/2-5)
            pt1 = (width/2,height/2+5)
            cv2.line(outputImg, pt0, pt1, ui.COLOR_PURPLE, 1)
            pt0 = (width/2-5,height/2)
            pt1 = (width/2+5,height/2)
            cv2.line(outputImg, pt0, pt1, ui.COLOR_PURPLE, 1)
            
            #Zone edges
            drawBorder(outputImg, z.poi, ui.COLOR_BLUE, 2)
            
            #Scan Area edges
            drawBorder(outputImg, z.scanarea, ui.COLOR_LBLUE, 2)

            #Last Known Bot Locations
            for bot in Arena.bot:
                if bot.zid == z.id:                
                    bot.drawLastKnownLoc(outputImg)
        
        #Merge images if Display: All
        if ui.display == -1:
            if allImg is None or z.id == 0: #not set or first
                allImg = zeros((height, width*Arena.numzones, 3), uint8)
            #print z.id, height, width, Arena.numzones, size(outputImg,0), size(outputImg,1)
            if size(outputImg,0) == height and size(outputImg,1) == width:
                allImg[0:height, (z.id*width):((z.id+1)*width)] = outputImg
            if z.id+1 == len(Arena.zone):   #last
                outputImg = allImg
    
    #End of zone loop
    
    #Read from each bots serial device
    for bot in Arena.bot:                   
        if bot.sdi != -1:
            data = bot.serial.readline()            
            if data.strip() == "$W":
                reply = "{0:["
                #{0:[[x, y, heading, alive, botid, teamid],...]}
                for sbot in Arena.bot:
                    reply += "["
                    reply += str(sbot.locZone[0])
                    reply += ","+str(sbot.locZone[1])
                    reply += ","+str(sbot.heading)
                    reply += ","+str(sbot.alive)
                    reply += ","+str(sbot.id)
                    reply += ","+str(sbot.id)
                    reply += "]"
                reply += "]}\n"
                print reply.strip()
                bot.serial.write(reply)
            else:
                print "'"+data.strip()+"'"
            
    controlPanelImg = ui.drawControlPanel(Arena)

    outputImg = ui.resize(outputImg)

    #Display the image or frame of video
    cv2.imshow("ArenaScanner", outputImg)
    cv2.imshow("ArenaControlPanel", controlPanelImg)

    ui.calcFPS()

    #Exit
    if ui.exit: 
        break
      
###############
## END LOOP
###############
for z in Arena.zone:
    z.close()
cv2.destroyAllWindows()

print "Exiting."



