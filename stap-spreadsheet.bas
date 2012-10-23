REM  *****  BASIC  *****
'Copyright (c) 2008 Winfried Rohr, re-Solutions Software Test Engineering
'mailto: ooo@re-solutions.de  Untere Zahlbacher Strasse 18, D-55131 Mainz

'importAllCSVFiles and createLinks - Copyright (c) 2012 Rich Megginson, Red Hat Inc.
'mailto: rmeggins@redhat.com
 
'This program is free software; you can redistribute it and/or modify it under 
'the terms of the GNU General Public License as published by the Free Software
'Foundation; either version 2 of the License, or (at your option) any later 
'version.

'This program is distributed in the hope that it will be useful, but WITHOUT 
'ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
'FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

'You should have received a copy of the GNU General Public License along with 
'this program; if not, write to the Free Software Foundation, Inc., 59 Temple 
'Place, Suite 330, Boston, MA 02111-1307 USA
' ========================================================================


' Main routine
'
' 1. Edit importAllCSVFiles to make sure you specify which directory
' contains the stap-report.py output in CSV files

' 2. run importAllCSVFiles from your target Calc document

' 3. run createLinks to create the forward and backwards
' links among and between the spreadsheets

Sub importAllCSVFiles
    Dim NextFile As String
    Dim MyDir As String

    oImport2Calc = StarDesktop.getCurrentComponent().getCurrentController().getModel()
    ' Examine whether Macro called is for a Calc Spreadsheet
    If NOT oImport2Calc.supportsService( "com.sun.star.sheet.SpreadsheetDocument" ) Then
        MsgBox _
        "Not CALC. Macro called is not for a Calc Spreadsheet." & CHR(10) _
        & CHR(10) & "Explanation:" _
        & CHR(10) & "This macro imports a CSV file with pre-defined filter" _
        & CHR(10) & "settings - but it was not called from a Calc document" _
        & CHR(10) _
        & CHR(10) & "Macro " & sMakroName & " is now finished." _
        , 48 , sMakroName & "Version " & sMakroVersion
        Exit Sub
        ' CALC SHEET HAS TO CALL THIS ROUTINE
    End If

    ' load of auxiliary functions library
    GlobalScope.BasicLibraries.LoadLibrary( "Tools" )

    MyDir = "/var/tmp/stacks/"
    ' do Summary first
    NextFile = "Summary.csv"
    insertCSV2Calc(MyDir, NextFile, oImport2Calc)
    ' next do MutexInitStacks
    NextFile = "MutexInitStacks.csv"
    insertCSV2Calc(MyDir, NextFile, oImport2Calc)
    ' next do contention stack files
    For II = 0 to 1000
        NextFile = "initstack-" & CStr(II) & ".csv"
        If Not FileExists(MyDir & NextFile) Then
            Exit For ' done
        End If
        insertCSV2Calc(MyDir, NextFile, oImport2Calc)
    Next II
End Sub

Sub insertCSV2Calc (myDir As String, myFile As String, oImport2Calc As Object)

sMakroName = "insertCSV2Calc "
'sMakroVersion = "1.4.2 " ' Niko plus ,4
sMakroVersion = "1.5.0 " ' Niko plus ,4
'sMakroDatum = "20070615 "
'sMakroDatum = "20080202 " ' 1.4.1 CopyError calling function name
'sMakroDatum = "20080711 " ' 1.4.2 typo "iiZeile"
sMakroDatum = "20081221 " ' 1.5.0 english messages, main translation by Mike Craven
' additional filter strings provided 
' Windows style drive:\directory strings

' compute sheet name from filename - filename minus ".csv"len
idx = InStr(myFile, ".csv")
if idx < 1 then
    Exit Sub
End If

sSheetName = Left(myFile, idx-1)
' if available: not OK

if oImport2Calc.Sheets().hasByName( sSheetName ) then
    MsgBox _
    "End the macro: Sheet already exists." & CHR(10) _
    & CHR(10) & "Explanation:" _
    & CHR(10) & "A Sheet with the name entered exists." _
    & CHR(10) & "Therefore no data was imported." _
    & CHR(10) & "Makro " & sMakroName & " is now finished." _
    , 48 , sMakroName & "Version " & sMakroVersion
    Exit Sub
End If

' sheet with given name does not exist:
' check if too much sheet already there
if oImport2Calc.Sheets().getCount() < 255 then
    oImport2Calc.Sheets().insertNewByName( sSheetName , oImport2Calc.Sheets().getCount() )
else
    MsgBox _
    "End the macro: Maximum number of sheets." & CHR(10) _
    & CHR(10) & "Explanation:" _
    & CHR(10) & "This Calc file has the maximum number of CALC sheets:" _
    & CHR(10) & "no new sheet for import can be inserted." _
    & CHR(10) & "Therefore no data was imported" _
    & CHR(10) & "Makro " & sMakroName & " is now finished." _
    , 48 , sMakroName & "Version " & sMakroVersion
    Exit Sub        
End If
        
' Object for the new sheet    
oNewSheet = oImport2Calc.Sheets().getByName( sSheetName )

' Determine Filter
Dim FileProperties(1) As New com.sun.star.beans.PropertyValue
FileProperties(0).Name = "FilterName"
FileProperties(0).Value ="Text - txt - csv (StarCalc)"
FileProperties(1).Name = "FilterOptions"
' FilterOptions
' 
' >>>>
' insert YOUR filter data here
' >>>>
FileProperties(1).Value = "44,34,1,1"

' Open File
sUrl = ConvertToUrl(myDir & myFile)
' MsgBox "filename " & myDir & myFile & " url " & sUrl
' oCSV = StarDesktop.loadComponentFromURL( _
'     myDir & sUrl, "_blank", 0, FileProperties())
oCSV = StarDesktop.loadComponentFromURL(sUrl, "_blank", 0, FileProperties())

' Identify the area of data
oSourceSheet = oCSV.Sheets( 0 )
    
Dim iiColumns as Long
Dim iiRows as Long
iiColumns = iC2C_getLastUsedColumn( oSourceSheet )
iiRows = iC2C_getLastUsedRow( oSourceSheet )

' pull out all data as an array
oSourceArea = oSourceSheet.getCellRangeByPosition( _
     0, 0, iiColumns, iiRows )

allData = oSourceArea.getDataArray()
        
' Target area in the same size set
oEndArea = oNewSheet.getCellRangeByPosition( _
     0, 0, iiColumns, iiRows )
     ' purely write Data array
     oEndArea.setDataArray( allData() )
    
' CSV file closed  
oCSV.close( TRUE )      

End Sub

' ========================================================================
' pure: Sheet as Object
' Out: Number of the last row / column (starting from zero)
Function iC2C_getLastUsedColumn(oSheet as Object) as Integer
Dim oCell As Object
Dim oCursor As Object
Dim aAddress As Variant
oCell = oSheet.GetCellbyPosition( 0, 0 )
oCursor = oSheet.createCursorByRange(oCell)
oCursor.GotoEndOfUsedArea(True)
aAddress = oCursor.RangeAddress
iC2C_getLastUsedColumn = aAddress.EndColumn
End Function

Function iC2C_getLastUsedRow(oSheet as Object) as Integer
Dim oCell As Object
Dim oCursor As Object
Dim aAddress As Variant
oCell = oSheet.GetCellbyPosition( 0, 0 )
oCursor = oSheet.createCursorByRange(oCell)
oCursor.GotoEndOfUsedArea(True)
aAddress = oCursor.RangeAddress
iC2C_GetLastUsedRow = aAddress.EndRow
End Function

' =========================
' To determine the filtering options for * your * CSV file: open it 
' (from OOo, with File>Open... dialogue, use the Import dialogue, '
' with all the necessary Settings), then run the following routine.
' Note the returned values (copy) and replace the ones coded above
' (search "FilterOptions")

' http://www.oooforum.org/forum/viewtopic.phtml?t=40544
' Villeroy Aug 02, 2006 12:08 am
Sub showFilterOptions
Dim args(),i%
   args() = thisComponent.getArgs
   for i = 0 to uBound(Args())
      if args(i).Name = "FilterOptions" then inputbox "","",args(i).value
   next
End Sub

' create links from the Summary page to the init stacks and contention stack sheets, and vice versa
Sub createLinks
   Dim Doc As Object
   Dim cssheets() As Object ' array of contention stack sheets
   ipref = "initstack-"
   cpref = "contstacks-"
   hyppref = "=HYPERLINK("""
   hypmid = """;"""
   hypsuf = """)"
   Doc = ThisComponent
   ' sheet names
   sum = Doc.Sheets.getByName("Summary")
   mis = Doc.Sheets.getByName("MutexInitStacks")
   nsheets = Doc.Sheets.getCount()
   Redim cssheets(nsheets) As Object
   realnsheets = 0
   For II = 0 to nsheets
       sname = ipref & CStr(II)
       If Doc.Sheets().hasByName(sname) Then
           cssheets(II) = Doc.Sheets.getByName(sname)
           realnsheets = realnsheets + 1
       End If
   Next II
   ' now loop through the Summary sheet
   ' for each item in the Init Stack column we want to create a link to the
   ' init stack in the MutexInitStack sheet, and vice versa
   ' for each item in the Cont. Stacks column we want to create a link to the
   ' contention stack sheet and vice versa
   ' for each contention stack sheet, for each Location, we want to create a
   ' link to the stack, and vice versa
   Dim scell As Object
   Dim ccell As Object
   sidx = 5
   cidx = 0
   misidx = 1
   Do
       isaddr = "A" & CStr(sidx)
       csaddr = "B" & CStr(sidx)
       scell = sum.getCellRangeByName(isaddr)
       If scell.Type = com.sun.star.table.CellContentType.EMPTY Then
           Exit Do
       End If
       ccell = sum.getCellRangeByName(csaddr)
       ' link ccell to the cont stacks sheet
       ' =HYPERLINK("#initstack-N";"contstacks-N")
       If ccell.Type <> com.sun.star.table.CellContentType.FORMULA Then
           ccell.Formula = hyppref & "#" & scell.String & hypmid & ccell.String & hypsuf
       End If
       cssheet = cssheets(cidx)
       cscell = cssheet.getCellRangeByName("A1")
       If cscell.Type <> com.sun.star.table.CellContentType.FORMULA Then
           cscell.Formula = hyppref & "#Summary." & csaddr & hypmid & cscell.String & hypsuf
       End If
       ' find cell containing "initstack-N" in the mis sheet
       Do
           ' look for two consecutive empty cells in the first column as the end of data
           misaddr = "A" & CStr(misidx)
           miscell = mis.getCellRangeByName(misaddr)
           If miscell.Type = com.sun.star.table.CellContentType.EMPTY Then
               misaddr = "A" & CStr(misidx + 1)
               miscell = mis.getCellRangeByName(misaddr)
               If miscell.Type = com.sun.star.table.CellContentType.EMPTY Then
                   Exit Do
               End If
           Else
               If miscell.String = scell.String Then
                   If miscell.Type <> com.sun.star.table.CellContentType.FORMULA Then
                       miscell.Formula = hyppref & "#Summary." & isaddr & hypmid & miscell.String & hypsuf
                   End If
                   If scell.Type <> com.sun.star.table.CellContentType.FORMULA Then
                       scell.Formula = hyppref & "#MutexInitStacks." & misaddr & hypmid & miscell.String & hypsuf
                   End If
                   misidx = misidx + 1
                   Exit Do
               End If
           End If
           misidx = misidx + 1
       Loop While True()
       sidx = sidx + 1
       cidx = cidx + 1
   Loop While True()
   ' on each contention stack page, create a link from the table to the
   ' particular contention stack and vice versa
   For II = 0 To realnsheets-1
       cssheet = cssheets(II)
       cidx = 4
       csidx = cidx + 1
       Do
           caddr = "A" & CStr(cidx)
           ccell = cssheet.getCellRangeByName(caddr)
           If ccell.Type = com.sun.star.table.CellContentType.EMPTY Then
               Exit Do
           End If
           Do
               csaddr = "A" & CStr(csidx)
               cscell = cssheet.getCellRangeByName(csaddr)
               If cscell.Type = com.sun.star.table.CellContentType.EMPTY Then
                   csaddr = "A" & CStr(csidx + 1)
                   cscell = cssheet.getCellRangeByName(csaddr)
                   If cscell.Type = com.sun.star.table.CellContentType.EMPTY Then
                       Exit Do
                   End If
               Else
                   If cscell.String = ccell.String Then
                       ' found match - create forward and back links
                       If ccell.Type <> com.sun.star.table.CellContentType.FORMULA Then
                           ccell.Formula = hyppref & "#" & csaddr & hypmid & ccell.String & hypsuf
                       End If
                       If cscell.Type <> com.sun.star.table.CellContentType.FORMULA Then
                           cscell.Formula = hyppref & "#" & caddr & hypmid & cscell.String & hypsuf
                       End If
                       csidx = csidx + 1
                       Exit Do
                   End If
               End If
               csidx = csidx + 1
           Loop While True()
           cidx = cidx + 1
       Loop While True()
   Next II
End Sub
