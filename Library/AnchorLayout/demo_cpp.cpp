#include "demo_cpp.h"
#include "ui_formmain.h"


FormMain::FormMain(QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::FormMain)
{
    ui->setupUi(this);
    this->anchorlayout=new AnchorLayout(this);
    this->anchorlayout->init();
}

//窗体大小改变
void FormMain::resizeEvent(QResizeEvent *event)
{
    this->anchorlayout->update();
}

FormMain::~FormMain()
{
    if(NULL != anchorlayout)
        delete anchorlayout;

    delete ui;
}

